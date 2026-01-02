import os
import pathlib
from pathlib import Path
import logging
import json
import time

logger = logging.getLogger(__name__)

# Define the path to the config file in the data directory
DATA_DIR = Path(os.getenv("DB_DATA_DIR", "/app/data"))  # Default to /app/data for dev
CONFIG_FILE_PATH = DATA_DIR / "config.json"

# Default settings
DEFAULT_SETTINGS = {
    "POLL_INTERVAL_MINUTES": 15,
    "RETENTION_DAYS": 30,
    "TEMP_MIN": 20,
    "TEMP_MAX": 70,
    "VOLT_MIN": 5.0,
    "BITAXE_ENDPOINTS": [],
    "DISCORD_WEBHOOK_URL": ""
}

def ensure_data_dir():
    """Ensure the data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def load_settings():
    """Load settings from JSON file in data directory"""
    ensure_data_dir()
    
    # If the file doesn't exist yet, create it with default settings
    if not CONFIG_FILE_PATH.exists():
        logger.info(f"No config file found at {CONFIG_FILE_PATH}, creating with defaults")
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    
    # Load settings from file
    try:
        logger.info(f"Loading settings from {CONFIG_FILE_PATH}")
        with open(CONFIG_FILE_PATH, 'r') as f:
            settings = json.load(f)
        
        # Ensure all required settings exist with defaults
        for key, default_value in DEFAULT_SETTINGS.items():
            if key not in settings:
                settings[key] = default_value
        
        # Ensure numeric values are properly converted
        try:
            settings["POLL_INTERVAL_MINUTES"] = int(settings["POLL_INTERVAL_MINUTES"])
            settings["RETENTION_DAYS"] = int(settings["RETENTION_DAYS"])
            settings["TEMP_MIN"] = float(settings["TEMP_MIN"])
            settings["TEMP_MAX"] = float(settings["TEMP_MAX"])
            settings["VOLT_MIN"] = float(settings["VOLT_MIN"])
            
            # Log the converted values for debugging
            logger.info(f"Loaded settings - POLL_INTERVAL_MINUTES: {settings['POLL_INTERVAL_MINUTES']}, "
                        f"VOLT_MIN: {settings['VOLT_MIN']}")
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting settings values: {e}, using defaults")
            # Use defaults for any values that couldn't be converted
            settings["POLL_INTERVAL_MINUTES"] = DEFAULT_SETTINGS["POLL_INTERVAL_MINUTES"]
            settings["RETENTION_DAYS"] = DEFAULT_SETTINGS["RETENTION_DAYS"]
            settings["TEMP_MIN"] = DEFAULT_SETTINGS["TEMP_MIN"]
            settings["TEMP_MAX"] = DEFAULT_SETTINGS["TEMP_MAX"]
            settings["VOLT_MIN"] = DEFAULT_SETTINGS["VOLT_MIN"]
        
        return settings
    except Exception as e:
        logger.exception(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings_dict):
    """Save settings to JSON file in data directory"""
    ensure_data_dir()
    
    # Convert string endpoints to list if needed
    if isinstance(settings_dict.get("BITAXE_ENDPOINTS"), str):
        endpoints = settings_dict["BITAXE_ENDPOINTS"].split(",")
        settings_dict["BITAXE_ENDPOINTS"] = [ep.strip() for ep in endpoints if ep.strip()]
    
    # Convert types to appropriate values
    try:
        settings_dict["POLL_INTERVAL_MINUTES"] = int(settings_dict.get("POLL_INTERVAL_MINUTES", DEFAULT_SETTINGS["POLL_INTERVAL_MINUTES"]))
        settings_dict["RETENTION_DAYS"] = int(settings_dict.get("RETENTION_DAYS", DEFAULT_SETTINGS["RETENTION_DAYS"]))
        settings_dict["TEMP_MIN"] = float(settings_dict.get("TEMP_MIN", DEFAULT_SETTINGS["TEMP_MIN"]))
        settings_dict["TEMP_MAX"] = float(settings_dict.get("TEMP_MAX", DEFAULT_SETTINGS["TEMP_MAX"]))
        settings_dict["VOLT_MIN"] = float(settings_dict.get("VOLT_MIN", DEFAULT_SETTINGS["VOLT_MIN"]))
        
        # Log the converted values for debugging
        logger.info(f"Saving settings - POLL_INTERVAL_MINUTES: {settings_dict['POLL_INTERVAL_MINUTES']}, "
                    f"VOLT_MIN: {settings_dict['VOLT_MIN']}")
    except (ValueError, TypeError) as e:
        logger.error(f"Error converting settings values: {e}")
        return False
    
    try:
        # Create a temporary file first to avoid corruption if the process is interrupted
        temp_file = CONFIG_FILE_PATH.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(settings_dict, f, indent=2)
        
        # Rename the temporary file to the actual config file
        temp_file.replace(CONFIG_FILE_PATH)
        
        logger.info(f"Settings saved to {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        logger.exception(f"Error saving settings: {e}")
        return False 