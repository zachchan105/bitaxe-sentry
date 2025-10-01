import datetime
import logging
import socket

import requests

from .config import DISCORD_WEBHOOK, reload_config

logger = logging.getLogger(__name__)

def send_startup_notification(service="main"):
    """
    Send a notification when the system starts up to verify webhook configuration.
    
    Args:
        service: The service that's starting ('main' or 'web')
    """
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    
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
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    
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
      f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V | Hash Rate: {reading.hash_rate:.2f} MH/s"
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
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    
    if not DISCORD_WEBHOOK:
        logger.warning(f"Discord webhook URL not configured, skipping diff alert for {miner.name}")
        return False
        
    logger.info(f"Preparing to send diff alert for {miner.name} via webhook: {DISCORD_WEBHOOK[:20]}...")
        
    content = (
      f"🎉 **{miner.name}** new best diff! {reading.best_diff}\n"
      f"Temperature: {reading.temperature:.1f}°C | Voltage: {reading.voltage:.2f}V | Hash Rate: {reading.hash_rate:.2f} MH/s"
    )
    
    try:
        response = requests.post(
            DISCORD_WEBHOOK, 
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"New best diff alert sent for {miner.name}: {reading.best_diff}")
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
        logger.info("Test notification sent successfully to webhook")
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
    # Reload config to ensure we have the latest webhook URL
    reload_config()
    
    if not DISCORD_WEBHOOK:
        logger.warning(f"Discord webhook URL not configured, skipping offline alert for {miner.name}")
        return False
        
    logger.info(f"Preparing to send offline alert for {miner.name} via webhook: {DISCORD_WEBHOOK[:20]}...")
    
    # Get the last reading time if available
    last_reading_time = "Unknown"
    try:
        from sqlmodel import select

        from .db import Reading, get_session
        
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