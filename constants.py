"""
Constants for the US Visa Appointment Slot Checker Bot
"""

# Version
import os
from dotenv import load_dotenv
VERSION = "2.0.0"
load_dotenv()

# Time intervals
DEFAULT_CHECK_INTERVAL =  int(os.getenv('CHECK_INTERVAL', '700')) 
DEFAULT_STEP_TIME = 5  # time between steps
MAX_SUBSCRIBERS = int(os.getenv('MAX_SUBSCRIBERS', '4'))

# Selectors
REGEX_CONTINUE = "//a[contains(text(),'Continue')]"