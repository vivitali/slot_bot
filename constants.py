"""
Constants for the US Visa Appointment Slot Checker Bot
"""

# Version
VERSION = "2.0.0"

# Time intervals
DEFAULT_CHECK_INTERVAL = 700  # 10 minutes in seconds
DEFAULT_EXCEPTION_TIME = 1800  # 30 minutes in seconds
DEFAULT_COOLDOWN_TIME = 3600  # 60 minutes in seconds
DEFAULT_STEP_TIME = 5  # time between steps

# Selectors
REGEX_CONTINUE = "//a[contains(text(),'Continue')]"