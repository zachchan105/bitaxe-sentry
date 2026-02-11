import requests
import logging
import json
import pathlib
import os
from .config import DISCORD_WEBHOOK, reload_config
import socket
import datetime

logger = logging.getLogger(__name__)

# Path to mute status file (stores per-miner mutes)
DATA_DIR = pathlib.Path(os.getenv("DB_DATA_DIR", "/app/data"))
MUTE_STATUS_FILE = DATA_DIR / "notification_mute.json"

def _load_mute_data():
    """Load mute data from file"""
    try:
        if not MUTE_STATUS_FILE.exists():
            return {}
        with open(MUTE_STATUS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading mute data: {e}")
        return {}

def _save_mute_data(mute_data):
    """Save mute data to file"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(MUTE_STATUS_FILE, 'w') as f:
            json.dump(mute_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving mute data: {e}")
        return False

def is_miner_muted(miner_id):
    """
    Check if notifications are currently muted for a specific miner.
    
    Args:
        miner_id: ID of the miner to check
    
    Returns:
        bool: True if notifications are muted for this miner, False otherwise
    """
    try:
        mute_data = _load_mute_data()
        miner_mutes = mute_data.get('miners', {})
        
        if str(miner_id) not in miner_mutes:
            return False
        
        mute_until = miner_mutes[str(miner_id)].get('mute_until', 0)
        current_time = int(datetime.datetime.utcnow().timestamp() * 1000)  # milliseconds
        
        if current_time < mute_until:
            remaining_ms = mute_until - current_time
            remaining_mins = remaining_ms / 60000
            logger.info(f"Miner {miner_id} notifications are muted for {remaining_mins:.1f} more minutes")
            return True
        else:
            # Mute expired, clean up
            mute_data = _load_mute_data()
            if 'miners' in mute_data and str(miner_id) in mute_data['miners']:
                del mute_data['miners'][str(miner_id)]
                _save_mute_data(mute_data)
            return False
    except Exception as e:
        logger.warning(f"Error checking mute status for miner {miner_id}: {e}")
        return False

def set_miner_mute(miner_id, minutes):
    """
    Set notification mute for a specific miner.
    
    Args:
        miner_id: ID of the miner to mute
        minutes: Number of minutes to mute notifications
    
    Returns:
        bool: True if successful, False otherwise
    """
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
    """
    Clear notification mute for a specific miner (unmute).
    
    Args:
        miner_id: ID of the miner to unmute
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        mute_data = _load_mute_data()
        if 'miners' in mute_data and str(miner_id) in mute_data['miners']:
            del mute_data['miners'][str(miner_id)]
            if _save_mute_data(mute_data):
                logger.info(f"Miner {miner_id} notifications unmuted")
                return True
        return True  # Already unmuted
    except Exception as e:
        logger.error(f"Error clearing mute for miner {miner_id}: {e}")
        return False

def format_difficulty_for_display(diff_value):
    """
    Format difficulty value for human-readable display.
    
    Args:
        diff_value: Difficulty value (string, typically normalized number)
    
    Returns:
        str: Formatted difficulty (e.g., "4.93G" or "1.05G")
    """
    try:
        num = float(diff_value)
        magnitude = abs(num)
        
        for unit, threshold in [('T', 1_000_000_000_000), ('G', 1_000_000_000), ('M', 1_000_000), ('K', 1_000)]:
            if magnitude >= threshold:
                return f"{num / threshold:.2f}{unit}"
        
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return str(diff_value)

def send_startup_notification(service="main"):
    """
    Send a notification when the system starts up to verify webhook configuration.
    
    Args:
        service: The service that's starting ('main' or 'web')
    """
    # Note: Startup notifications are not muted - they're important for verifying webhook config
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    from .config import DISCORD_WEBHOOK
    
    if not DISCORD_WEBHOOK:
        logger.warning("Discord webhook URL not configured, skipping startup notification")
        return False
        
    logger.info(f"Sending startup notification to webhook: {DISCORD_WEBHOOK[:20]}...")
        
    hostname = socket.gethostname()
    try:
        ip_address = socket.gethostbyname(hostname)
    except:
        ip_address = "unknown"
    
    service_name = "Web UI" if service == "web" else "Monitor"
    
    content = (
      f"🚀 **Bitaxe Sentry {service_name}** started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
      f"✅ Discord notifications are working correctly!"
    )
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Startup notification for {service_name} sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
        return False


def send_alert(miner, reading, alert_type="temperature"):
    """
    Send temperature or voltage alert via Discord webhook.
    
    Args:
        miner: The miner instance
        reading: Reading instance with temperature/voltage data
        alert_type: Type of alert ("temperature" or "voltage")
    """
    # Check if notifications are muted for this miner
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} (ID: {miner.id}) notifications are muted, skipping {alert_type} alert")
        return False
    
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    from .config import DISCORD_WEBHOOK
    
    if not DISCORD_WEBHOOK:
        logger.warning(f"Discord webhook URL not configured, skipping {alert_type} alert for {miner.name}")
        return False
    
    logger.info(f"Preparing to send {alert_type} alert for {miner.name} via webhook: {DISCORD_WEBHOOK[:20]}...")
    
    if alert_type == "temperature":
        emoji = "🔥"
        message = f"⚠️ **{miner.name}** temperature out of range: {reading.temperature:.1f}°C"
    elif alert_type == "voltage":
        emoji = "⚡"
        message = f"⚠️ **{miner.name}** voltage out of range: {reading.voltage:.2f}V"
    else:
        logger.error(f"Unknown alert type: {alert_type}")
        return False
        
    content = (
      f"{message}\n"
      f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V | Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"{alert_type.capitalize()} alert sent for {miner.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send {alert_type} alert: {e}")
        return False


def send_voltage_alert(miner, reading):
    """
    Send voltage alert via Discord webhook.
    
    Args:
        miner: The miner instance
        reading: Reading instance with voltage data
    """
    return send_alert(miner, reading, alert_type="voltage")


def send_temperature_alert(miner, reading):
    """
    Send temperature alert via Discord webhook.
    
    Args:
        miner: The miner instance
        reading: Reading instance with temperature data
    """
    return send_alert(miner, reading, alert_type="temperature")


def send_diff_alert(miner, reading):
    """
    Send new best difficulty notification via Discord webhook.
    
    Args:
        miner: The miner instance
        reading: Reading instance with best_diff data
    """
    # Check if notifications are muted for this miner
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} (ID: {miner.id}) notifications are muted, skipping diff alert")
        return False
    
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    from .config import DISCORD_WEBHOOK
    
    if not DISCORD_WEBHOOK:
        logger.warning(f"Discord webhook URL not configured, skipping diff alert for {miner.name}")
        return False
        
    logger.info(f"Preparing to send diff alert for {miner.name} via webhook: {DISCORD_WEBHOOK[:20]}...")
    
    # Format difficulty for display
    formatted_diff = format_difficulty_for_display(reading.best_diff)
        
    content = (
      f"🎉 **{miner.name}** new best diff! {formatted_diff}\n"
      f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V | Hash Rate: {reading.hash_rate:.2f} GH/s"
    )
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"New best diff alert sent for {miner.name}: {formatted_diff}")
        return True
    except Exception as e:
        logger.error(f"Failed to send best diff alert: {e}")
        return False

def send_test_notification(webhook_url):
    """
    Send a test notification to verify webhook configuration.
    
    Args:
        webhook_url: The webhook URL to test
        
    Returns:
        bool: True if successful, False otherwise
    """
    # For test notifications, we use the provided webhook URL directly
    # No need to reload config since the URL is passed as a parameter
    
    if not webhook_url:
        logger.warning("No webhook URL provided for test")
        return False
        
    logger.info(f"Sending test notification to webhook: {webhook_url[:20]}...")
        
    content = (
      f"🧪 **Bitaxe Sentry Test Notification**\n"
      f"✅ This is a test message sent at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
      f"✅ Discord webhook is configured correctly!"
    )
    
    try:
        response = requests.post(
            webhook_url, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Test notification sent successfully to webhook")
        return True
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        return False

def send_miner_offline_alert(miner):
    """
    Send an alert when a miner fails to respond to polling.
    
    Args:
        miner: The miner instance that failed to respond
        
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    # Check if notifications are muted for this miner
    if is_miner_muted(miner.id):
        logger.info(f"Miner {miner.name} (ID: {miner.id}) notifications are muted, skipping offline alert")
        return False
    
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    from .config import DISCORD_WEBHOOK
    
    if not DISCORD_WEBHOOK:
        logger.warning(f"Discord webhook URL not configured, skipping offline alert for {miner.name}")
        return False
        
    logger.info(f"Preparing to send offline alert for {miner.name} via webhook: {DISCORD_WEBHOOK[:20]}...")
    
    # Get the last reading time if available
    last_reading_time = "Unknown"
    try:
        from sqlmodel import select
        from .db import get_session, Reading
        
        with get_session() as session:
            last_reading = session.exec(
                select(Reading)
                .where(Reading.miner_id == miner.id)
                .order_by(Reading.timestamp.desc())
                .limit(1)
            ).first()
            
            if last_reading:
                last_reading_time = last_reading.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"Failed to get last reading time for offline miner: {e}")
    
    content = (
      f"🔴 **{miner.name}** is **OFFLINE**\n"
      f"Failed to respond to latest polling event"
    )
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Offline alert sent for {miner.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send offline alert: {e}")
        return False 