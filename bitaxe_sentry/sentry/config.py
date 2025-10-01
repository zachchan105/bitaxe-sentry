import logging
import os

from .settings_manager import load_settings

logger = logging.getLogger(__name__)

# Load settings from JSON config file
settings = load_settings()

# Configuration parameters with default values
POLL_INTERVAL = settings["POLL_INTERVAL_MINUTES"]
logger.info(f"Configured polling interval: {POLL_INTERVAL} minutes")

RETENTION_DAYS = settings["RETENTION_DAYS"]
TEMP_MIN = settings["TEMP_MIN"]
TEMP_MAX = settings["TEMP_MAX"]
VOLT_MIN = settings["VOLT_MIN"]

# Process endpoints
ENDPOINTS = []
for ep in settings["BITAXE_ENDPOINTS"]:
    ep = ep.strip()
    if ep:
        # Ensure each endpoint has a protocol
        if not ep.startswith(("http://", "https://")):
            ep = f"http://{ep}"
        ENDPOINTS.append(ep)

logger.info(f"Configured endpoints: {ENDPOINTS}")

# Discord webhook
DISCORD_WEBHOOK = settings["DISCORD_WEBHOOK_URL"]
if DISCORD_WEBHOOK:
    logger.info(f"Discord webhook configured: {DISCORD_WEBHOOK[:20]}...")
else:
    logger.info("Discord webhook not configured")

# Track when config was last modified

def get_config_mtime():
    """Get the modification time of the config file"""
    from .settings_manager import CONFIG_FILE_PATH
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            return os.path.getmtime(CONFIG_FILE_PATH)
        return 0
    except Exception:
        return 0

# Initialize last modified time
last_modified_time = get_config_mtime()

def reload_config():
    """Reload configuration from JSON config file if it has been modified"""
    global POLL_INTERVAL, RETENTION_DAYS, TEMP_MIN, TEMP_MAX, VOLT_MIN, ENDPOINTS, DISCORD_WEBHOOK, last_modified_time
    
    # Check if the config file has been modified
    current_mtime = get_config_mtime()
    if current_mtime <= last_modified_time:
        # File hasn't been modified, no need to reload
        return False
    
    logger.info("Reloading configuration...")
    
    # Load settings from file
    settings = load_settings()
    
    # Now update global variables from settings
    POLL_INTERVAL = settings["POLL_INTERVAL_MINUTES"]
    RETENTION_DAYS = settings["RETENTION_DAYS"]
    TEMP_MIN = settings["TEMP_MIN"]
    TEMP_MAX = settings["TEMP_MAX"]
    VOLT_MIN = settings["VOLT_MIN"]
    DISCORD_WEBHOOK = settings["DISCORD_WEBHOOK_URL"]
    
    # Process endpoints
    ENDPOINTS.clear()
    for ep in settings["BITAXE_ENDPOINTS"]:
        ep = ep.strip()
        if ep:
            # Ensure each endpoint has a protocol
            if not ep.startswith(("http://", "https://")):
                ep = f"http://{ep}"
            ENDPOINTS.append(ep)
    
    # Update the last modified time
    last_modified_time = current_mtime
    
    logger.info("Updated configuration:")
    logger.info(f"- Poll interval: {POLL_INTERVAL} minutes")
    logger.info(f"- Retention days: {RETENTION_DAYS}")
    logger.info(f"- Temperature range: {TEMP_MIN}°C - {TEMP_MAX}°C")
    logger.info(f"- Minimum voltage: {VOLT_MIN}V")
    logger.info(f"- Endpoints: {ENDPOINTS}")
    
    # Log Discord webhook status
    if DISCORD_WEBHOOK:
        logger.info(f"- Discord webhook updated: {DISCORD_WEBHOOK[:20]}...")
    else:
        logger.info("- Discord webhook not configured")
    
    return True 