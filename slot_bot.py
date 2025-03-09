#!/usr/bin/env python3
"""
US Visa Appointment Slot Checker Bot
------------------------------------
This script monitors the US visa appointment website for available slots
using direct HTTP requests for data retrieval and Selenium for authentication and form submissions.

Designed for deployment on Google Cloud Compute Engine.
"""

import json
import os
import platform
import random
import socket
import time
from datetime import datetime, timedelta

import pytz
import schedule
from selenium.webdriver.common.by import By
# Selenium related imports
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from telegram import Bot
from telegram.constants import ParseMode
# Telegram related imports
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler

from config_loader import load_config
# Import from our modules
from constants import VERSION, REGEX_CONTINUE
from setup_driver import setup_driver
from setup_logger import setup_logging
from utils import get_random_interval

# Import the SessionManager and appointment checker functions
from session_manager import SessionManager
from appointment_checker import get_available_dates, get_available_times

# Initialize logger
logger = setup_logging()

# Load configuration
CONFIG = load_config()

# Generate URLs based on configuration
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{CONFIG['COUNTRY_CODE']}/niv/schedule/{CONFIG['SCHEDULE_ID']}/appointment"

# Initialize global variables
driver = None
session_manager = None
last_seen = None
last_notification_time = None
EXIT = False

# Initialize the Telegram bot
def send_telegram_notification(message):
    """Send a notification via Telegram."""
    global last_notification_time
    
    # Check if we should throttle notifications
    current_time = datetime.now()
    if last_notification_time and (current_time - last_notification_time).total_seconds() < CONFIG.get('NOTIFICATION_COOLDOWN', 300):
        logger.info(f"Notification cooldown active. Not sending: {message}")
        return False
    
    try:
        logger.info(f"Sending Telegram notification: {message}")
        bot = Bot(token=CONFIG['TELEGRAM_TOKEN'])
        
        # Add hostname and time info
        hostname = socket.gethostname()
        tz = pytz.timezone(CONFIG['TIMEZONE'])
        local_time = current_time.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
        
        full_message = f"{message}\n\nTime: {local_time}\nBot: {hostname} (v{VERSION})"
        
        # Send message with formatting
        bot.send_message(
            chat_id=CONFIG['CHAT_ID'], 
            text=full_message, 
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        last_notification_time = current_time
        logger.info("Telegram notification sent successfully")
        return True
    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {e}")
        return False

def initialize_session():
    """Initialize or refresh the session."""
    global driver, session_manager
    
    try:
        logger.info("Initializing or refreshing session...")
        
        # Create session manager if it doesn't exist
        if session_manager is None:
            session_manager = SessionManager(
                username=CONFIG['USERNAME'], 
                password=CONFIG['PASSWORD'], 
                country_code=CONFIG['COUNTRY_CODE']
            )
        
        # Try direct requests login first (faster and more efficient)
      # Initialize WebDriver if needed
        if driver is None or not is_driver_active():
            driver = setup_driver()
            if driver is None:
                raise Exception("Failed to set up WebDriver")
        
        # Perform login with Selenium
        if not session_manager.is_logged_in(driver):
            if session_manager.login_with_selenium(driver):
                logger.info("Login with Selenium successful")
                return True
        
        logger.error("All login methods failed")
        return False
        
    except Exception as e:
        logger.error(f"Error during session initialization: {e}")
        
        try:
            if driver is not None:
                driver.save_screenshot('session_error.png')
                logger.info("Error screenshot saved as session_error.png")
        except:
            pass
            
        return False

def is_driver_active():
    """Check if the WebDriver is still active and usable."""
    try:
        if driver is None:
            return False
        # Try to get the current URL to check if driver is responsive
        _ = driver.current_url
        return True
    except:
        return False

def get_date():
    """Get available appointment dates using HTTP requests."""
    global session_manager
    
    try:
        logger.info("Checking for available appointment dates...")
        
        # Ensure we have a valid session
        if session_manager is None or not session_manager.is_logged_in(driver): 
            logger.warning("Session invalid or not initialized")
            if not initialize_session():
                logger.error("Failed to initialize session")
                return []
        
        # Get session details
        session_cookie, csrf_token = session_manager.get_session_details()
        
        if not session_cookie or not csrf_token:
            logger.error("Missing session cookie or CSRF token")
            return []
        
        # Use HTTP request to get dates
        dates = get_available_dates(
            session_cookie=session_cookie,
            csrf_token=csrf_token,
            schedule_id=CONFIG['SCHEDULE_ID'],
            facility_id=CONFIG['FACILITY_ID'],
            country_code=CONFIG['COUNTRY_CODE']
        )
        
        # If no dates or error, try refreshing the session once
        if not dates:
            logger.warning("No dates returned, trying to refresh session...")
            if initialize_session():
                session_cookie, csrf_token = session_manager.get_session_details()
                
                # Try again with refreshed session
                dates = get_available_dates(
                    session_cookie=session_cookie,
                    csrf_token=csrf_token,
                    schedule_id=CONFIG['SCHEDULE_ID'],
                    facility_id=CONFIG['FACILITY_ID'],
                    country_code=CONFIG['COUNTRY_CODE']
                )
        
        logger.info(f"Found {len(dates)} available dates")
        return dates
        
    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        
        # Take a screenshot if possible
        try:
            if driver is not None:
                driver.save_screenshot('date_error.png')
        except:
            pass
            
        return []

def get_time(date):
    """Get available appointment times for a given date using HTTP requests."""
    global session_manager
    
    try:
        logger.info(f"Getting available times for date: {date}")
        
        # Ensure we have a valid session
        if session_manager is None or not session_manager.is_session_valid():
            logger.warning("Session invalid or not initialized")
            if not initialize_session():
                logger.error("Failed to initialize session")
                return None
        
        # Get session details
        session_cookie, csrf_token = session_manager.get_session_details()
        
        # Use HTTP request to get times
        available_times = get_available_times(
            session_cookie=session_cookie,
            csrf_token=csrf_token,
            schedule_id=CONFIG['SCHEDULE_ID'],
            facility_id=CONFIG['FACILITY_ID'],
            date=date,
            country_code=CONFIG['COUNTRY_CODE']
        )
        
        if not available_times:
            logger.warning(f"No available times found for date {date}")
            return None
            
        # Get the last time slot (usually latest in the day)
        time_slot = available_times[-1]
        logger.info(f"Selected time slot: {date} {time_slot}")
        
        return time_slot
        
    except Exception as e:
        logger.error(f"Error getting available times: {e}")
        return None

def reschedule(date):
    """Reschedule appointment to the given date."""
    global EXIT, driver, session_manager
    
    try:
        logger.info(f"Starting reschedule process for date: {date}")
        
        # Get an available time slot
        time_slot = get_time(date)
        if not time_slot:
            logger.error("Could not get time slot, aborting reschedule")
            return False
        
        # For reschedule, we need to use Selenium as it's a more complex form submission
        # Ensure we have a valid driver and session
        if driver is None or not is_driver_active():
            logger.info("Initializing WebDriver for reschedule...")
            driver = setup_driver()
            if driver is None:
                raise Exception("Failed to set up WebDriver")
            
            # Ensure we have a valid session
            if session_manager is None or not session_manager.is_session_valid():
                if not initialize_session():
                    raise Exception("Failed to initialize session for reschedule")
        
        # Navigate to the appointment page
        logger.info("Navigating to appointment page...")
        driver.get(APPOINTMENT_URL)
        time.sleep(random.uniform(2, 4))
        
        try:
            # Get form data
            logger.debug("Getting form data...")
            data = {
                "utf8": driver.find_element(by=By.NAME, value='utf8').get_attribute('value'),
                "authenticity_token": driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value'),
                "confirmed_limit_message": driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value'),
                "use_consulate_appointment_capacity": driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value'),
                "appointments[consulate_appointment][facility_id]": CONFIG['FACILITY_ID'],
                "appointments[consulate_appointment][date]": date,
                "appointments[consulate_appointment][time]": time_slot,
            }
            
            # Get cookies for the request
            cookies = {"_yatri_session": driver.get_cookie("_yatri_session")["value"]}
            
            # Prepare headers
            headers = {
                "User-Agent": driver.execute_script("return navigator.userAgent;"),
                "Referer": APPOINTMENT_URL,
                "X-CSRF-Token": data["authenticity_token"],
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml"
            }
            
            # Update session manager with latest session info
            session_manager.session_cookie = cookies["_yatri_session"]
            session_manager.csrf_token = data["authenticity_token"]
            
            # Submit the reschedule request
            logger.info("Submitting reschedule request...")
            import requests
            response = requests.post(
                APPOINTMENT_URL,
                data=data,
                headers=headers,
                cookies=cookies,
                allow_redirects=True
            )
            
            # Check if reschedule was successful
            if 'Successfully Scheduled' in response.text:
                msg = f"✅ *Appointment Rescheduled!*\n\nNew appointment date: *{date}*\nTime: *{time_slot}*"
                send_telegram_notification(msg)
                
                # Take a screenshot of the confirmation
                try:
                    driver.get(APPOINTMENT_URL)  # Refresh to see confirmation
                    time.sleep(3)
                    driver.save_screenshot('reschedule_success.png')
                    logger.info("Saved confirmation screenshot")
                except:
                    pass
                    
                EXIT = True
                return True
            else:
                msg = f"❌ *Reschedule Failed*\n\nAttempted date: *{date}*\nTime: *{time_slot}*\n\nThe slot may have been taken by someone else."
                send_telegram_notification(msg)
                return False
                
        except Exception as e:
            logger.error(f"Error during reschedule form submission: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error during reschedule process: {e}")
        return False

def print_dates(dates):
    """Log available dates for debugging."""
    logger.info("Available dates:")
    for d in dates:
        logger.info(f"{d.get('date')} \t business_day: {d.get('business_day')}")

def is_date_suitable(date):
    """Check if a date is suitable for rescheduling based on custom conditions."""
    global last_seen
    
    try:
        # Check if this is a new date we haven't seen before
        if date == last_seen:
            logger.info(f"Date {date} already seen, skipping")
            return False
            
        # Check if the new date is earlier than current appointment
        current_date = datetime.strptime(CONFIG['MY_SCHEDULE_DATE'], "%Y-%m-%d")
        new_date = datetime.strptime(date, "%Y-%m-%d")

        # Get today's date
        today = datetime.now()
        future_date = today + timedelta(days=5)
        
        if current_date <= new_date and new_date >= future_date:
            logger.info(f"Date {date} is not earlier than current appointment {CONFIG['MY_SCHEDULE_DATE']}")
            return False
            
        # Apply custom date filtering if defined
        year, month, day = date.split('-')
        
        # Custom condition can be defined here
        # For example: return int(month) == 11 and int(day) >= 5
        
        # Default: accept any earlier date
        logger.info(f"Date {date} is suitable for rescheduling")
        last_seen = date
        return True
        
    except Exception as e:
        logger.error(f"Error checking date suitability: {e}")
        return False

def get_available_date(dates):
    """Find the earliest suitable date from available dates."""
    logger.info("Checking for an earlier and suitable date...")
    
    for d in dates:
        date = d.get('date')
        if is_date_suitable(date):
            return date
    
    return None

def setup_telegram_bot():
    """Initialize and start Telegram bot for commands."""
    try:
        logger.info("Setting up Telegram bot...")
        updater = Updater(CONFIG['TELEGRAM_TOKEN'])
        dispatcher = updater.dispatcher
        
        # Define command handlers
        def start(update, context):
            update.message.reply_text(
                f"👋 Hello! I'm the US Visa Slot Checker Bot (v{VERSION}).\n\n"
                "I'll notify you when new visa appointment slots become available.\n\n"
                "Commands:\n"
                "/check - Check for available slots now\n"
                "/status - Get current bot status\n"
                "/help - Show this help message"
            )
        
        def check_now(update, context):
            update.message.reply_text("🔍 Checking for available slots now...")
            
            # Run a check in a separate thread to not block the bot
            context.bot_data['checking'] = True
            
            try:
                dates = get_date()[:10]  # Get top 10 dates
                
                if not dates:
                    update.message.reply_text("❗ No available dates found. The website may be experiencing issues.")
                    return
                
                date_strings = []
                for d in dates[:5]:  # Show top 5 dates
                    date_str = d.get('date')
                    date_strings.append(f"• {date_str}")
                
                date_list = "\n".join(date_strings)
                
                suitable_date = get_available_date(dates)
                if suitable_date:
                    update.message.reply_text(
                        f"✅ *Suitable slot found!*\n\n"
                        f"Date: *{suitable_date}*\n\n"
                        f"Available dates:\n{date_list}\n\n"
                        f"Do you want me to reschedule? Reply with /reschedule to confirm.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    # Store the date for potential reschedule
                    context.bot_data['reschedule_date'] = suitable_date
                else:
                    update.message.reply_text(
                        f"👎 No suitable slots found yet.\n\n"
                        f"Available dates:\n{date_list}\n\n"
                        f"I'll continue monitoring and notify you when a suitable slot becomes available.",
                        parse_mode=ParseMode.MARKDOWN
                    )
            finally:
                context.bot_data['checking'] = False
        
        def reschedule_command(update, context):
            if 'reschedule_date' not in context.bot_data:
                update.message.reply_text("❌ No date selected for rescheduling. Please use /check first.")
                return
                
            date = context.bot_data['reschedule_date']
            update.message.reply_text(f"🔄 Attempting to reschedule to {date}...")
            
            success = reschedule(date)
            if success:
                update.message.reply_text("✅ Appointment successfully rescheduled!")
            else:
                update.message.reply_text("❌ Failed to reschedule. The slot may no longer be available.")
                
            # Clear the stored date
            del context.bot_data['reschedule_date']
        
        def status(update, context):
            # Get system info
            hostname = socket.gethostname()
            uptime = os.popen('uptime -p').read()[:-1] if platform.system() != "Windows" else "N/A"
            
            # Get bot status
            is_checking = context.bot_data.get('checking', False)
            
            # Get session status
            session_valid = "Yes" if session_manager and session_manager.is_session_valid() else "No"
            
            update.message.reply_text(
                f"📊 *Bot Status*\n\n"
                f"Version: {VERSION}\n"
                f"Host: {hostname}\n"
                f"Uptime: {uptime}\n"
                f"Current appointment: {CONFIG['MY_SCHEDULE_DATE']}\n"
                f"Session valid: {session_valid}\n"
                f"Check interval: {CONFIG['CHECK_INTERVAL']} seconds\n"
                f"Currently checking: {'Yes' if is_checking else 'No'}\n\n"
                f"Next automatic check: {get_next_check_time()}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        def help_command(update, context):
            update.message.reply_text(
                "🔹 *US Visa Slot Checker Bot Help* 🔹\n\n"
                "This bot monitors the US visa appointment website for available slots and notifies you when they become available.\n\n"
                "*Commands:*\n"
                "/start - Start the bot\n"
                "/check - Check for available slots now\n"
                "/reschedule - Confirm rescheduling to the last found slot\n"
                "/status - Get current bot status\n"
                "/help - Show this help message\n\n"
                "The bot automatically checks for new slots at regular intervals.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Register handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("check", check_now))
        dispatcher.add_handler(CommandHandler("reschedule", reschedule_command))
        dispatcher.add_handler(CommandHandler("status", status))
        dispatcher.add_handler(CommandHandler("help", help_command))
        
        # Start the Bot in a separate thread
        updater.start_polling()
        logger.info("Telegram bot started and polling for commands!")
        
        return updater
        
    except Exception as e:
        logger.error(f"Failed to set up Telegram bot: {e}")
        return None

def get_next_check_time():
    """Get the time until the next scheduled check."""
    for job in schedule.jobs:
        return job.next_run.strftime("%H:%M:%S")
    return "Unknown"

def check_appointments():
    """Main function to check for appointments and reschedule if found."""
    global EXIT
    
    try:
        logger.info("Starting appointment check...")
        
        # Get available dates using HTTP request
        dates = get_date()[:10]  # Limit to top 10 dates
        
        if not dates:
            logger.warning("No dates returned from the website. Possible temporary ban or site issue.")
            msg = "⚠️ *Warning*\n\nNo appointment dates returned from the website. This could indicate a temporary IP ban or website maintenance. Will try again later."
            send_telegram_notification(msg)
            
            # Sleep for cooldown period
            logger.info(f"Sleeping for cooldown period: {CONFIG['COOLDOWN_TIME']} seconds")
            time.sleep(CONFIG['COOLDOWN_TIME'])
            return
        
        # Print dates for logging
        print_dates(dates[:5])
        
        # Find a suitable date
        suitable_date = get_available_date(dates)
        logger.info(f"Suitable date found: {suitable_date}")
        
        if suitable_date:
            # Try to reschedule
            reschedule(suitable_date)
        else:
            logger.info("No suitable dates found. Will check again later.")
        
        if EXIT:
            logger.info("Exit flag set. Stopping regular checks.")
            return
            
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
        EXIT = True
    except Exception as e:
        logger.error(f"Error during appointment check: {e}")
        
        # Take a screenshot if possible
        try:
            if driver is not None:
                driver.save_screenshot(f'error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        except:
            pass
            
        # Send error notification
        msg = f"⚠️ *Error During Check*\n\nThe bot encountered an error:\n`{str(e)}`\n\nWill retry later."
        send_telegram_notification(msg)
        
        # Sleep for exception time
        logger.info(f"Sleeping for exception time: {CONFIG['EXCEPTION_TIME']} seconds")
        time.sleep(CONFIG['EXCEPTION_TIME'])

def cleanup():
    """Clean up resources before exit."""
    global driver
    
    try:
        if driver is not None:
            logger.info("Closing WebDriver...")
            driver.quit()
    except:
        pass
    
    logger.info("Cleanup complete")

def main():
    """Main entry point for the application."""
    global driver, EXIT, session_manager
    
    try:
        # Print startup banner
        print(f"=" * 60)
        print(f"  US Visa Slot Checker Bot v{VERSION}")
        print(f"  Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=" * 60)
        
        # Initialize session
        session_manager = SessionManager(
            username=CONFIG['USERNAME'],
            password=CONFIG['PASSWORD'],
            country_code=CONFIG['COUNTRY_CODE']
        )
        
        # Try to initialize session (first with requests, then with Selenium if needed)
        if not initialize_session():
            raise Exception("Failed to initialize session")
        
        # Set up Telegram bot
        telegram_bot = setup_telegram_bot()
        
        # Send startup notification
        send_telegram_notification(
            "🚀 *Bot Started* 🚀\n\n"
            f"The US Visa Slot Checker Bot v{VERSION} has been started and is now monitoring for available appointment slots."
        )
        
        # Schedule regular checks
        schedule.every(CONFIG['CHECK_INTERVAL']).seconds.do(check_appointments)
        logger.info(f"Scheduled automatic checks every {CONFIG['CHECK_INTERVAL']} seconds")
        
        # First check immediately on startup
        check_appointments()
        
        # Main loop
        retry_count = 0
        max_retries = 6
        
        while not EXIT and retry_count <= max_retries:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Process interrupted by user.")
                EXIT = True
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in main loop (retry {retry_count}/{max_retries}): {e}")
                time.sleep(CONFIG['EXCEPTION_TIME'])
        
        if retry_count > max_retries:
            logger.critical("Too many errors. Exiting.")
            send_telegram_notification("💥 *Bot Crashed*\n\nToo many errors occurred. The bot has stopped running. Please check the logs and restart manually.")
        
        # Cleanup
        cleanup()
        
        # Stop Telegram bot
        if telegram_bot is not None:
            telegram_bot.stop()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        send_telegram_notification("⚠️ *Bot Stopped*\n\nThe bot has been manually stopped.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        send_telegram_notification(f"💥 *FATAL ERROR*\n\nThe bot has encountered a fatal error and has stopped:\n`{str(e)}`")
    finally:
        cleanup()

if __name__ == "__main__":
    main()