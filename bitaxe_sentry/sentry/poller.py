import requests
import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlmodel import Session, select
from .config import ENDPOINTS, TEMP_MAX, TEMP_MIN, TEMP_VR_MAX, VOLT_MIN, LATENCY_MAX_THRESHOLD, LATENCY_CONSECUTIVE_COUNT, reload_config
from .db import engine, Miner, Reading
from .notifier import (
    send_temperature_alert, send_voltage_alert, send_diff_alert,
    send_miner_offline_alert, send_latency_alert, send_pool_failover_alert,
    send_vr_temp_alert,
)

logger = logging.getLogger(__name__)

consecutive_latency_failures: dict[int, int] = {}
consecutive_offline_failures: dict[int, int] = {}

# Minimum consecutive offline polls before alerting (avoids single-packet-drop spam)
OFFLINE_CONSECUTIVE_COUNT = 2


def poll_endpoint(endpoint_url):
    try:
        resp = requests.get(f"{endpoint_url}/api/system/info", timeout=10)
        resp.raise_for_status()
        return {'success': True, 'endpoint': endpoint_url, 'data': resp.json()}
    except Exception as e:
        return {'success': False, 'endpoint': endpoint_url, 'error': str(e)}


def normalize_difficulty(diff_value):
    """Normalize difficulty to a raw number string (handles SI suffixes like 4.93G)."""
    if diff_value is None:
        return "0"

    diff_str = str(diff_value).strip()

    try:
        num = float(diff_str)
        return str(int(num))
    except (ValueError, TypeError):
        pass

    match = re.match(r'^([\d.]+)\s*([KMGTPEkmgtpe]?)$', diff_str, re.IGNORECASE)
    if match:
        number_part = float(match.group(1))
        unit_part = match.group(2).upper() if match.group(2) else ''
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'G': 1_000_000_000,
            'T': 1_000_000_000_000,
            'P': 1_000_000_000_000_000,
            'E': 1_000_000_000_000_000_000,
            '': 1,
        }
        multiplier = multipliers.get(unit_part, 1)
        return str(int(number_part * multiplier))

    logger.warning(f"Could not normalize difficulty value: {diff_value}, storing as-is")
    return diff_str


def _coerce_flag(value) -> bool:
    """Coerce firmware boolean-ish values (0/1/"true"/etc.) to Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _build_active_pool_url(data: dict) -> tuple[str | None, bool]:
    """Return (active_pool_url, using_fallback) from raw API data."""
    using_fallback = _coerce_flag(data.get("isUsingFallbackStratum"))

    if using_fallback:
        host = data.get("fallbackStratumURL") or data.get("fallbackStratumUrl") or ""
        port = data.get("fallbackStratumPort")
    else:
        host = data.get("stratumURL") or data.get("stratumUrl") or ""
        port = data.get("stratumPort")

    if not host:
        return None, using_fallback

    if port:
        return f"{host}:{port}", using_fallback
    return host, using_fallback


def poll_once():
    """Poll all configured miners once and store results. Returns success count."""
    logger.info("Starting polling cycle")

    reload_config()
    from .config import ENDPOINTS, TEMP_MAX, TEMP_MIN, TEMP_VR_MAX, VOLT_MIN, LATENCY_MAX_THRESHOLD, LATENCY_CONSECUTIVE_COUNT

    if not ENDPOINTS:
        logger.warning("No miner endpoints configured, skipping poll")
        return 0

    success_count = 0

    poll_results = []
    with ThreadPoolExecutor(max_workers=len(ENDPOINTS)) as executor:
        futures = {executor.submit(poll_endpoint, ep): ep for ep in ENDPOINTS}
        for future in as_completed(futures):
            result = future.result()
            poll_results.append(result)
            if result['success']:
                success_count += 1

    with Session(engine) as session:
        for result in poll_results:
            endpoint_url = result['endpoint']

            if not result['success']:
                logger.error(f"Failed to poll miner at {endpoint_url}: {result['error']}")

                miner = session.exec(select(Miner).where(Miner.endpoint == endpoint_url)).first()
                if miner:
                    count = consecutive_offline_failures.get(miner.id, 0) + 1
                    consecutive_offline_failures[miner.id] = count
                    logger.warning(
                        f"Miner {miner.name} offline (consecutive: {count})"
                    )
                    if count >= OFFLINE_CONSECUTIVE_COUNT:
                        try:
                            send_miner_offline_alert(miner)
                        except Exception as alert_error:
                            logger.exception(f"Failed to send offline alert for {miner.name}: {alert_error}")
                        consecutive_offline_failures[miner.id] = 0
                continue

            # Miner is online — reset its offline counter
            miner = session.exec(select(Miner).where(Miner.endpoint == endpoint_url)).first()
            if not miner:
                logger.info(f"Registering new miner at {endpoint_url}")
                miner = Miner(name=f"bitaxe_{endpoint_url.split('://')[-1]}", endpoint=endpoint_url)
                session.add(miner)
                session.commit()
                session.refresh(miner)

            consecutive_offline_failures[miner.id] = 0

            data = result['data']

            # Voltage
            raw_voltage = data.get("voltage", 0.0)
            converted_voltage = raw_voltage / 1000.0 if raw_voltage else 0.0
            logger.info(f"Raw voltage: {raw_voltage}, Converted: {converted_voltage}V, Min threshold: {VOLT_MIN}V")

            # Pool latency
            response_time = data.get("responseTime", None)

            # Difficulty
            raw_best_diff = data.get("bestDiff", "0")
            normalized_best_diff = normalize_difficulty(raw_best_diff)

            # Best diff since restart (bestSessionDiff; fall back to bestDiff)
            raw_session_diff = data.get("bestSessionDiff") or data.get("bestSessiondiff")
            best_session_diff = normalize_difficulty(raw_session_diff) if raw_session_diff else None

            # VR temperature (voltage regulator)
            vr_temp_raw = data.get("vrTemp")
            vr_temp = None
            if vr_temp_raw is not None:
                try:
                    v = float(vr_temp_raw)
                    vr_temp = v if v > 0 else None  # firmware reports -1 for absent sensor
                except (TypeError, ValueError):
                    pass

            # Fan
            fan_rpm = data.get("fanrpm")
            if fan_rpm is not None:
                try:
                    fan_rpm = int(fan_rpm)
                except (TypeError, ValueError):
                    fan_rpm = None
            fan_pct_raw = data.get("fanspeed")
            fan_pct = None
            if fan_pct_raw is not None:
                try:
                    fan_pct = float(fan_pct_raw)
                except (TypeError, ValueError):
                    fan_pct = None

            # Pool / stratum
            pool_url, using_fallback = _build_active_pool_url(data)

            r = Reading(
                miner_id=miner.id,
                hash_rate=data["hashRate"],
                temperature=data["temp"],
                vr_temp=vr_temp,
                best_diff=normalized_best_diff,
                voltage=converted_voltage,
                error_percentage=data.get("errorPercentage", 0.0),
                response_time=response_time,
                fan_rpm=fan_rpm,
                fan_pct=fan_pct,
                pool_url=pool_url,
                using_fallback=using_fallback,
                best_session_diff=best_session_diff,
            )
            session.add(r)
            session.commit()

            # ── Chip temperature alert ────────────────────────────────────
            if r.temperature > TEMP_MAX or r.temperature < TEMP_MIN:
                logger.warning(
                    f"Temperature out of range for {miner.name}: {r.temperature}°C "
                    f"(range: {TEMP_MIN}-{TEMP_MAX}°C)"
                )
                send_temperature_alert(miner, r)

            # ── VR temperature alert ───────────────────────────────────────
            if r.vr_temp is not None and r.vr_temp >= TEMP_VR_MAX:
                logger.warning(
                    f"VR temperature critical for {miner.name}: {r.vr_temp:.1f}°C "
                    f"(threshold: {TEMP_VR_MAX}°C)"
                )
                try:
                    send_vr_temp_alert(miner, r)
                except Exception as e:
                    logger.exception(f"Failed to send VR temp alert for {miner.name}: {e}")

            # ── Voltage alert ──────────────────────────────────────────────
            if r.voltage < VOLT_MIN:
                logger.warning(f"Voltage below minimum for {miner.name}: {r.voltage}V (min: {VOLT_MIN}V)")
                try:
                    send_voltage_alert(miner, r)
                except Exception as e:
                    logger.exception(f"Failed to send voltage alert for {miner.name}: {e}")

            # ── Pool latency alert ─────────────────────────────────────────
            if r.response_time is not None:
                if r.response_time > LATENCY_MAX_THRESHOLD:
                    consecutive_latency_failures[miner.id] = (
                        consecutive_latency_failures.get(miner.id, 0) + 1
                    )
                    logger.warning(
                        f"Pool latency above threshold for {miner.name}: {r.response_time}ms "
                        f"(threshold: {LATENCY_MAX_THRESHOLD}ms) "
                        f"[consecutive: {consecutive_latency_failures[miner.id]}]"
                    )
                    if consecutive_latency_failures[miner.id] >= LATENCY_CONSECUTIVE_COUNT:
                        try:
                            send_latency_alert(miner, r, consecutive_latency_failures[miner.id])
                        except Exception as e:
                            logger.exception(f"Failed to send latency alert for {miner.name}: {e}")
                        consecutive_latency_failures[miner.id] = 0
                else:
                    if consecutive_latency_failures.get(miner.id, 0) > 0:
                        logger.info(f"Pool latency returned to normal for {miner.name}")
                    consecutive_latency_failures[miner.id] = 0

            # ── Pool failover alert ────────────────────────────────────────
            prev_reading = session.exec(
                select(Reading)
                .where(Reading.miner_id == miner.id, Reading.id != r.id)
                .order_by(Reading.timestamp.desc())
                .limit(1)
            ).first()

            if prev_reading is not None:
                prev_fallback = prev_reading.using_fallback
                curr_fallback = r.using_fallback
                if prev_fallback is not None and curr_fallback is not None:
                    if not prev_fallback and curr_fallback:
                        logger.warning(f"{miner.name} switched to fallback pool: {r.pool_url}")
                        try:
                            send_pool_failover_alert(miner, r, to_fallback=True)
                        except Exception as e:
                            logger.exception(f"Failed to send pool failover alert: {e}")
                    elif prev_fallback and not curr_fallback:
                        logger.info(f"{miner.name} returned to primary pool: {r.pool_url}")
                        try:
                            send_pool_failover_alert(miner, r, to_fallback=False)
                        except Exception as e:
                            logger.exception(f"Failed to send pool recovery alert: {e}")

                # ── New best diff alert ──────────────────────────────────
                prev_normalized = normalize_difficulty(prev_reading.best_diff)
                new_normalized = normalize_difficulty(r.best_diff)
                if prev_normalized != new_normalized:
                    logger.info(f"New best diff for {miner.name}: {new_normalized} (was {prev_normalized})")
                    send_diff_alert(miner, r)

    logger.info(f"Completed polling cycle. Successful: {success_count}/{len(ENDPOINTS)}")
    return success_count
