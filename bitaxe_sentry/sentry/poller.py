import requests
import datetime
import logging
import re
from sqlmodel import Session, select
from .config import ENDPOINTS, TEMP_MAX, TEMP_MIN, VOLT_MIN, reload_config
from .db import engine, Miner, Reading
from .notifier import send_temperature_alert, send_voltage_alert, send_diff_alert, send_miner_offline_alert

logger = logging.getLogger(__name__)

def normalize_difficulty(diff_value):
    """
    Normalize difficulty value to a consistent format (raw number as string).
    
    Handles both old firmware format (e.g., "4.93G") and new firmware format (e.g., "1051806384").
    
    Args:
        diff_value: Difficulty value from API (can be string like "4.93G" or "1051806384")
    
    Returns:
        str: Normalized difficulty as raw number string
    """
    if diff_value is None:
        return "0"
    
    # Convert to string if not already
    diff_str = str(diff_value).strip()
    
    # If it's already a pure number (new firmware format), return as-is
    try:
        # Try to parse as float first to handle numeric strings
        num = float(diff_str)
        # If it's a valid number without units, return it as integer string
        return str(int(num))
    except (ValueError, TypeError):
        pass
    
    # Handle old firmware format with units (e.g., "4.93G", "1.5M", "500K")
    # Match pattern like "4.93G" or "1.5M" or "500K"
    match = re.match(r'^([\d.]+)\s*([KMGTPEkmgtpe]?)$', diff_str, re.IGNORECASE)
    if match:
        number_part = float(match.group(1))
        unit_part = match.group(2).upper() if match.group(2) else ''
        
        # Multiplier map
        multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'G': 1_000_000_000,
            'T': 1_000_000_000_000,
            'P': 1_000_000_000_000_000,
            'E': 1_000_000_000_000_000_000,
            '': 1
        }
        
        multiplier = multipliers.get(unit_part, 1)
        normalized = int(number_part * multiplier)
        return str(normalized)
    
    # If we can't parse it, log a warning and return as-is
    logger.warning(f"Could not normalize difficulty value: {diff_value}, storing as-is")
    return diff_str

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
                
                # Normalize difficulty to handle both old and new firmware formats
                raw_best_diff = data.get("bestDiff", "0")
                normalized_best_diff = normalize_difficulty(raw_best_diff)
                logger.info(f"Raw best diff: {raw_best_diff}, Normalized: {normalized_best_diff}")
                
                # Create reading
                r = Reading(
                    miner_id=miner.id,
                    hash_rate=data["hashRate"],
                    temperature=data["temp"],
                    best_diff=normalized_best_diff,
                    voltage=converted_voltage,  # Convert from millivolts to volts
                    error_percentage=data.get("errorPercentage", 0.0)  # Error percentage
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
                
                # Normalize both values for comparison to handle mixed old/new format data
                if prev_reading:
                    prev_normalized = normalize_difficulty(prev_reading.best_diff)
                    new_normalized = normalize_difficulty(r.best_diff)
                    if prev_normalized != new_normalized:
                        logger.info(f"New best diff for {miner.name}: {new_normalized} (was {prev_normalized})")
                        send_diff_alert(miner, r)
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to poll miner at {endpoint_url}: {e}")
                
                # Send offline alert when miner fails to respond
                if miner:
                    logger.warning(f"Miner {miner.name} appears to be offline, sending alert")
                    try:
                        send_miner_offline_alert(miner)
                    except Exception as alert_error:
                        logger.exception(f"Failed to send offline alert for {miner.name}: {alert_error}")
                        
            except Exception as e:
                logger.exception(f"Error processing miner at {endpoint_url}: {e}")
    
    logger.info(f"Completed polling cycle. Successful: {success_count}/{len(ENDPOINTS)}")
    return success_count 