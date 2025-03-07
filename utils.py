"""
Utility functions for the US Visa Appointment Slot Checker Bot
"""

import random

def get_random_interval(max_interval: int) -> int:
    """
    Generate a random interval between 48.5% of max_interval and max_interval seconds
    """
    min_interval = int(max_interval * 0.1485)

    return random.randint(min_interval, max_interval)