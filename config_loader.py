"""
Configuration loading module for the US Visa Appointment Slot Checker Bot
"""
import logging
import os

from dotenv import load_dotenv
from constants import DEFAULT_CHECK_INTERVAL, DEFAULT_EXCEPTION_TIME, DEFAULT_COOLDOWN_TIME, DEFAULT_STEP_TIME
from utils import get_random_interval

logger = logging.getLogger(__name__)


def load_config():
    load_dotenv()
    """Load configuration from .env file"""
    # Required parameters
    required_params = ['VISA_USERNAME', 'VISA_PASSWORD', 'SCHEDULE_ID', 'FACILITY_ID', 'TELEGRAM_TOKEN', 'CHAT_ID']
    missing_params = [param for param in required_params if not os.getenv(param)]
    
    if missing_params:
        logger.error(f"Missing required parameters in .env file: {', '.join(missing_params)}")
        raise ValueError(f"Missing required environment variables: {', '.join(missing_params)}")
    
        
    config = {
        'USERNAME': os.getenv('VISA_USERNAME'),
        'PASSWORD': os.getenv('VISA_PASSWORD'),
        'SCHEDULE_ID': os.getenv('SCHEDULE_ID'),
        'MY_SCHEDULE_DATE': os.getenv('MY_SCHEDULE_DATE'),
        'COUNTRY_CODE': os.getenv('COUNTRY_CODE', 'en-ca'),
        'FACILITY_ID': os.getenv('FACILITY_ID'),
        'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
        'CHAT_ID': os.getenv('CHAT_ID'),
        'TIMEZONE': os.getenv('TIMEZONE', 'America/Toronto'),
        'CHECK_INTERVAL': get_random_interval(int(os.getenv('CHECK_INTERVAL', str(DEFAULT_CHECK_INTERVAL)))),
        'EXCEPTION_TIME': int(os.getenv('EXCEPTION_TIME', str(DEFAULT_EXCEPTION_TIME))),
        'COOLDOWN_TIME': int(os.getenv('COOLDOWN_TIME', str(DEFAULT_COOLDOWN_TIME))),
        'STEP_TIME': get_random_interval(int(os.getenv('STEP_TIME', str(DEFAULT_STEP_TIME)))),
        'LOCAL_USE': os.getenv('LOCAL_USE', 'true').lower() == 'true',
        'HUB_ADDRESS': os.getenv('HUB_ADDRESS', 'http://localhost:4444/wd/hub'),
        'HEADLESS': os.getenv('HEADLESS', 'true').lower() == 'true',
        'DEBUG_MODE': os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    }
    
    # If any essential config is missing, try config.ini
    if not all([config['USERNAME'], config['PASSWORD'], config['SCHEDULE_ID'], 
                config['FACILITY_ID'], config['TELEGRAM_TOKEN'], config['CHAT_ID']]):
        raise ValueError("Missing essential configuration in .env file")
        
    return config
    