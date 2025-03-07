"""
Configuration loading module for the US Visa Appointment Slot Checker Bot
"""
import logging
import os
import sys
import configparser
from constants import DEFAULT_CHECK_INTERVAL, DEFAULT_EXCEPTION_TIME, DEFAULT_COOLDOWN_TIME, DEFAULT_STEP_TIME
from utils import get_random_interval

logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from .env file or config.ini"""
    try:
        # First try to load from .env file
        from dotenv import load_dotenv
        load_dotenv()
        
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
    
    except (ImportError, ValueError) as e:
        logger.warning(f"Could not load config from .env: {e}")
        logger.info("Trying to load from config.ini...")
        
        try:
            config_parser = configparser.ConfigParser()
            config_parser.read('config.ini')
            
            config = {
                'USERNAME': config_parser['USVISA']['USERNAME'],
                'PASSWORD': config_parser['USVISA']['PASSWORD'],
                'SCHEDULE_ID': config_parser['USVISA']['SCHEDULE_ID'],
                'MY_SCHEDULE_DATE': config_parser['USVISA']['MY_SCHEDULE_DATE'],
                'COUNTRY_CODE': config_parser['USVISA'].get('COUNTRY_CODE', 'en-ca'),
                'FACILITY_ID': config_parser['USVISA']['FACILITY_ID'],
                'TELEGRAM_TOKEN': config_parser['TELEGRAM']['TELEGRAM_TOKEN'],
                'CHAT_ID': config_parser['TELEGRAM']['CHAT_ID'],
                'TIMEZONE': config_parser['SETTINGS'].get('TIMEZONE', 'America/Toronto'),
                'CHECK_INTERVAL': int(config_parser['SETTINGS'].get('CHECK_INTERVAL', str(DEFAULT_CHECK_INTERVAL))),
                'EXCEPTION_TIME': int(config_parser['SETTINGS'].get('EXCEPTION_TIME', str(DEFAULT_EXCEPTION_TIME))),
                'COOLDOWN_TIME': int(config_parser['SETTINGS'].get('COOLDOWN_TIME', str(DEFAULT_COOLDOWN_TIME))),
                'STEP_TIME': float(config_parser['SETTINGS'].get('STEP_TIME', str(DEFAULT_STEP_TIME))),
                'LOCAL_USE': config_parser['CHROMEDRIVER'].getboolean('LOCAL_USE', True),
                'HUB_ADDRESS': config_parser['CHROMEDRIVER'].get('HUB_ADDRESS', 'http://localhost:4444/wd/hub'),
                'HEADLESS': config_parser['CHROMEDRIVER'].getboolean('HEADLESS', True),
                'DEBUG_MODE': config_parser['SETTINGS'].getboolean('DEBUG_MODE', False)
            }
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)