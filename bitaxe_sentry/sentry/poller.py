import requests
import datetime
import logging
from sqlmodel import Session, select
from .config import ENDPOINTS, TEMP_MAX, TEMP_MIN, VOLT_MIN, reload_config
from .db import engine, Miner, Reading
from .notifier import send_temperature_alert, send_voltage_alert, send_diff_alert

logger = logging.getLogger(__name__)

def poll_once():
    """
    Poll all configured miner endpoints once and store results.
    Send alerts if thresholds are exceeded.
    """
    logger.info("Starting polling cycle")
    
    # Force reload config to ensure we have the latest settings
    reload_config()
    
    # Get the latest thresholds after reload
    from .config import ENDPOINTS, TEMP_MAX, TEMP_MIN, VOLT_MIN
    
    # Check if there are any endpoints configured
    if not ENDPOINTS:
        logger.warning("No miner endpoints configured, skipping poll")
        return 0
        
    success_count = 0
    
    with Session(engine) as session:
        for endpoint_url in ENDPOINTS:
            try:
                # Get or create miner record
                miner = session.exec(select(Miner).where(Miner.endpoint == endpoint_url)).first()
                if not miner:
                    logger.info(f"Registering new miner at {endpoint_url}")
                    miner = Miner(name=f"bitaxe_{endpoint_url.split('://')[-1]}", endpoint=endpoint_url)
                    session.add(miner)
                    session.commit()
                    # Refresh to get the ID
                    session.refresh(miner)
                
                # Poll miner API
                logger.info(f"Polling miner at {endpoint_url}")
                resp = requests.get(f"{endpoint_url}/api/system/info", timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                # Log raw voltage data for debugging
                raw_voltage = data.get("voltage", 0.0)
                converted_voltage = raw_voltage / 1000.0 if raw_voltage else 0.0
                logger.info(f"Raw voltage: {raw_voltage}, Converted: {converted_voltage}V, Min threshold: {VOLT_MIN}V")
                
                # Create reading
                r = Reading(
                    miner_id=miner.id,
                    hash_rate=data["hashRate"],
                    temperature=data["temp"],
                    best_diff=data["bestDiff"],
                    voltage=converted_voltage  # Convert from millivolts to volts
                )
                session.add(r)
                session.commit()
                success_count += 1
                
                # Temperature alerts
                if r.temperature > TEMP_MAX or r.temperature < TEMP_MIN:
                    logger.warning(f"Temperature out of range for {miner.name}: {r.temperature}°C (range: {TEMP_MIN}-{TEMP_MAX}°C)")
                    send_temperature_alert(miner, r)
                
                # Voltage alerts
                if r.voltage < VOLT_MIN:
                    logger.warning(f"Voltage below minimum for {miner.name}: {r.voltage}V (min: {VOLT_MIN}V)")
                    try:
                        send_voltage_alert(miner, r)
                        logger.info(f"Voltage alert sent for {miner.name}")
                    except Exception as e:
                        logger.exception(f"Failed to send voltage alert for {miner.name}: {e}")
                else:
                    logger.info(f"Voltage OK for {miner.name}: {r.voltage}V (min: {VOLT_MIN}V)")
                
                # New best diff check
                prev_reading = session.exec(
                    select(Reading)
                    .where(Reading.miner_id == miner.id, Reading.id != r.id)
                    .order_by(Reading.timestamp.desc())
                    .limit(1)
                ).first()
                
                if prev_reading and r.best_diff != prev_reading.best_diff:
                    logger.info(f"New best diff for {miner.name}: {r.best_diff}")
                    send_diff_alert(miner, r)
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to poll miner at {endpoint_url}: {e}")
            except Exception as e:
                logger.exception(f"Error processing miner at {endpoint_url}: {e}")
    
    logger.info(f"Completed polling cycle. Successful: {success_count}/{len(ENDPOINTS)}")
    return success_count 