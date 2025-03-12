"""
Utility functions for the US Visa Appointment Slot Checker Bot
"""

import random

def get_random_interval(max_interval: int) -> int:
    """
    Generate a random interval between 48.5% of max_interval and max_interval seconds
    """
    min_interval = int(max_interval * 0.485)

    return random.randint(min_interval, max_interval)

from datetime import datetime

def is_earlier_date(last_available_date: str, earlier_appointment: str) -> bool:
    """
    Compare two dates and return True if last_available_date is earlier than earlier_appointment.
    
    Args:
        last_available_date (str): Date string in format 'YYYY-MM-DD'
        earlier_appointment (str): Date string in format 'YYYY-MM-DD'
        
    Returns:
        bool: True if last_available_date is earlier than earlier_appointment, False otherwise
    """
    # Convert string dates to datetime objects for comparison
    last_date = datetime.strptime(last_available_date, '%Y-%m-%d')
    earlier_date = datetime.strptime(earlier_appointment, '%Y-%m-%d')
    
    # Compare dates
    return last_date < earlier_date