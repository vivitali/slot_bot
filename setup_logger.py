#!/usr/bin/env python3
"""
US Visa Appointment Slot Checker Bot with Selenium
--------------------------------------------------
This script monitors the US visa appointment website for available slots
using Selenium for web automation and sends notifications via Telegram.

Designed for deployment on Google Cloud Compute Engine.
"""

from logging.handlers import RotatingFileHandler
import os
import logging


# Configure logging
def setup_logging():
    """Configure logging for both file and console output."""
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'visa_bot.log')

    # Create formatters and handlers
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # File handler with rotation (10MB per file, max 5 files)
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Disable verbose logging from external libraries
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    return logging.getLogger(__name__)
