import requests
import logging
import json
import pathlib
import os
from .config import DISCORD_WEBHOOK, reload_config
import socket
import datetime

logger = logging.getLogger(__name__)

DATA_DIR = pathlib.Path(os.getenv("DB_DATA_DIR", "/app/data"))
MUTE_STATUS_FILE = DATA_DIR / "notification_mute.json"


def _load_mute_data():
    try:
        if not MUTE_STATUS_FILE.exists():
            return {}
        with open(MUTE_STATUS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading mute data: {e}")
        return {}


def _save_mute_data(mute_data):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(MUTE_STATUS_FILE, 'w') as f:
            json.dump(mute_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving mute data: {e}")
        return False


def is_miner_muted(miner_id):
    try:
        mute_data = _load_mute_data()
        miner_mutes = mute_data.get('miners', {})

        if str(miner_id) not in miner_mutes:
            return False

        mute_until = miner_mutes[str(miner_id)].get('mute_until', 0)
        current_time = int(datetime.datetime.utcnow().timestamp() * 1000)

        if current_time < mute_until:
            remaining_ms = mute_until - current_time
            remaining_mins = remaining_ms / 60000
            logger.info(f"Miner {miner_id} notifications are muted for {remaining_mins:.1f} more minutes")
            return True
        else:
            mute_data = _load_mute_data()
            if 'miners' in mute_data and str(miner_id) in mute_data['miners']:
                del mute_data['miners'][str(miner_id)]
                _save_mute_data(mute_data)
            return False
    except Exception as e:
        logger.warning(f"Error checking mute status for miner {miner_id}: {e}")
        return False


def set_miner_mute(miner_id, minutes):
    try:
        mute_data = _load_mute_data()
        if 'miners' not in mute_data:
            mute_data['miners'] = {}

        mute_until = int(datetime.datetime.utcnow().timestamp() * 1000) + (minutes * 60 * 1000)
        mute_data['miners'][str(miner_id)] = {
            'mute_until': mute_until,
            'muted_at': int(datetime.datetime.utcnow().timestamp() * 1000),
            'duration_minutes': minutes
        }

        if _save_mute_data(mute_data):
            logger.info(f"Miner {miner_id} notifications muted for {minutes} minutes")
            return True
        return False
    except Exception as e:
        logger.error(f"Error setting mute for miner {miner_id}: {e}")
        return False


def clear_miner_mute(miner_id):
    try:
        mute_data = _load_mute_data()
        if 'miners' in mute_data and str(miner_id) in mute_data['miners']:
            del mute_data['miners'][str(miner_id)]
            if _save_mute_data(mute_data):
                logger.info(f"Miner {miner_id} notifications unmuted")
                return True
        return True
    except Exception as e:
        logger.error(f"Error clearing mute for miner {miner_id}: {e}")
        return False


def format_difficulty_for_display(diff_value):
    try:
        num = float(diff_value)
        magnitude = abs(num)

        for unit, threshold in [('T', 1_000_000_000_000), ('G', 1_000_000_000), ('M', 1_000_000), ('K', 1_000)]:
            if magnitude >= threshold:
                return f"{num / threshold:.2f}{unit}"

        return f"{num:.2f}"
    except (ValueError, TypeError):
        return str(diff_value)


# ── Delivery helpers ──────────────────────────────────────────────────────────

def _send_discord(content: str) -> bool:
    reload_config()
    from .config import DISCORD_WEBHOOK
    if not DISCORD_WEBHOOK:
        return False
    try:
        resp = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Discord delivery failed: {e}")
        return False


def _send_ntfy(title: str, body: str, priority: str = "default") -> bool:
    """Send a notification to an ntfy topic."""
    reload_config()
    from .config import NTFY_TOPIC, NTFY_SERVER
    if not NTFY_TOPIC:
        return False
    server = (NTFY_SERVER or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{NTFY_TOPIC}"
    try:
        resp = requests.post(
            url,
            data=body.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "bitcoin,miner",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"ntfy delivery failed: {e}")
        return False


def _notify(content: str, title: str = "Bitaxe Sentry", priority: str = "default") -> bool:
    """Deliver to all configured channels (Discord + ntfy)."""
    discord_ok = _send_discord(content)
    ntfy_ok = _send_ntfy(title, content, priority)
    return discord_ok or ntfy_ok


# ── Public alert functions ────────────────────────────────────────────────────

def send_startup_notification(service="main"):
    reload_config()
    from .config import DISCORD_WEBHOOK, NTFY_TOPIC
    if not DISCORD_WEBHOOK and not NTFY_TOPIC:
        logger.warning("No notification channels configured, skipping startup notification")
        return False

    hostname = socket.gethostname()
    try:
        ip_address = socket.gethostbyname(hostname)
    except Exception:
        ip_address = "unknown"

    service_name = "Web UI" if service == "web" else "Monitor"
    content = (
        f"🚀 **Bitaxe Sentry {service_name}** started at "
        f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"✅ Notifications are working correctly!"
    )
    return _notify(content, title=f"Bitaxe Sentry {service_name} started")


def send_temperature_alert(miner, reading):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping temperature alert")
        return False
    content = (
        f"🔥 **{miner.name}** temperature out of range: {reading.temperature:.1f}°C\n"
        f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V "
        f"| Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    logger.info(f"Sending temperature alert for {miner.name}")
    return _notify(content, title=f"{miner.name}: Temperature alert", priority="high")


def send_voltage_alert(miner, reading):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping voltage alert")
        return False
    content = (
        f"⚡ **{miner.name}** voltage out of range: {reading.voltage:.2f}V\n"
        f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V "
        f"| Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    logger.info(f"Sending voltage alert for {miner.name}")
    return _notify(content, title=f"{miner.name}: Voltage alert", priority="high")


def send_diff_alert(miner, reading):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping diff alert")
        return False
    formatted_diff = format_difficulty_for_display(reading.best_diff)
    content = (
        f"🎉 **{miner.name}** new best diff! {formatted_diff}\n"
        f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V "
        f"| Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    logger.info(f"Sending diff alert for {miner.name}: {formatted_diff}")
    return _notify(content, title=f"{miner.name}: New best diff {formatted_diff}")


def send_miner_offline_alert(miner):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping offline alert")
        return False
    content = (
        f"🔴 **{miner.name}** is **OFFLINE**\n"
        f"Failed to respond to latest polling event"
    )
    logger.info(f"Sending offline alert for {miner.name}")
    return _notify(content, title=f"{miner.name}: OFFLINE", priority="urgent")


def send_latency_alert(miner, reading, consecutive_count=1):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping latency alert")
        return False
    reload_config()
    from .config import LATENCY_MAX_THRESHOLD
    content = (
        f"⚠️ **{miner.name}** high pool latency detected ({consecutive_count} consecutive)\n"
        f"Pool Latency: {reading.response_time:.1f}ms (threshold: {LATENCY_MAX_THRESHOLD}ms)\n"
        f"This may indicate network issues or pool connectivity problems."
    )
    logger.info(f"Sending latency alert for {miner.name}")
    return _notify(content, title=f"{miner.name}: High pool latency", priority="default")


def send_vr_temp_alert(miner, reading):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping VR temp alert")
        return False
    reload_config()
    from .config import TEMP_VR_MAX
    content = (
        f"🌡️ **{miner.name}** VR temperature critical: {reading.vr_temp:.1f}°C "
        f"(threshold: {TEMP_VR_MAX}°C)\n"
        f"Chip: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V "
        f"| Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    logger.info(f"Sending VR temp alert for {miner.name}: {reading.vr_temp:.1f}°C")
    return _notify(content, title=f"{miner.name}: VR temp critical", priority="urgent")


def send_pool_failover_alert(miner, reading, to_fallback: bool):
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} muted, skipping pool failover alert")
        return False
    pool = reading.pool_url or "unknown pool"
    if to_fallback:
        content = (
            f"⚠️ **{miner.name}** switched to **fallback pool**\n"
            f"Pool: {pool}"
        )
        title = f"{miner.name}: Switched to fallback pool"
        priority = "high"
    else:
        content = (
            f"✅ **{miner.name}** returned to **primary pool**\n"
            f"Pool: {pool}"
        )
        title = f"{miner.name}: Returned to primary pool"
        priority = "default"
    logger.info(f"Sending pool failover alert for {miner.name} (to_fallback={to_fallback})")
    return _notify(content, title=title, priority=priority)


def send_test_notification(webhook_url):
    """Test a specific Discord webhook URL."""
    if not webhook_url:
        logger.warning("No webhook URL provided for test")
        return False
    content = (
        f"🧪 **Bitaxe Sentry Test Notification**\n"
        f"✅ This is a test message sent at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"✅ Discord webhook is configured correctly!"
    )
    try:
        resp = requests.post(webhook_url, json={"content": content}, timeout=10)
        resp.raise_for_status()
        logger.info("Test notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        return False


def send_test_ntfy(ntfy_server, ntfy_topic):
    """Test a specific ntfy server/topic."""
    if not ntfy_topic:
        return False
    server = (ntfy_server or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{ntfy_topic}"
    body = (
        f"Bitaxe Sentry Test Notification\n"
        f"Sent at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"ntfy notifications are configured correctly!"
    )
    try:
        resp = requests.post(
            url,
            data=body.encode("utf-8"),
            headers={
                "Title": "Bitaxe Sentry Test",
                "Tags": "white_check_mark,bitcoin",
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("ntfy test notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send ntfy test notification: {e}")
        return False
