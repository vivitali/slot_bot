#!/usr/bin/env python3
"""
US Visa Appointment Slot Checker Bot with Selenium
--------------------------------------------------
This script monitors the US visa appointment website for available slots
using Selenium for web automation and sends notifications via Telegram.

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

# Initialize logger
logger = setup_logging()

# Load configuration
CONFIG = load_config()

# Generate URLs based on configuration
DATE_URL = f"https://ais.usvisa-info.com/{CONFIG['COUNTRY_CODE']}/niv/schedule/{CONFIG['SCHEDULE_ID']}/appointment/days/{CONFIG['FACILITY_ID']}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{CONFIG['COUNTRY_CODE']}/niv/schedule/{CONFIG['SCHEDULE_ID']}/appointment/times/{CONFIG['FACILITY_ID']}.json?date=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{CONFIG['COUNTRY_CODE']}/niv/schedule/{CONFIG['SCHEDULE_ID']}/appointment"

# Initialize global variables
driver = None
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
        time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
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


def login():
    """Log in to the US visa website."""
    global driver
    
    try:
        logger.info("Starting login process...")
        
        # Ensure we have a driver
        if driver is None or not is_driver_active():
            driver = setup_driver()
            if driver is None:
                raise Exception("Failed to set up WebDriver")

        # https://ais.usvisa-info.com/en-ca/niv/users/sign_in
        # Bypass reCAPTCHA
        driver.get(f"https://ais.usvisa-info.com/{CONFIG['COUNTRY_CODE']}/niv/users/sign_in")
        time.sleep(get_random_interval(CONFIG['STEP_TIME']))
        
        try:
            a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
            a.click()
            time.sleep(get_random_interval(CONFIG['STEP_TIME']))
        except Exception as e:
            logger.warning(f"Could not find bounce arrow: {e}")
            # Continue anyway
        
        # logger.info("Navigating to login page...")
        # href = driver.find_element(By.XPATH, '//*[@id="header"]/nav/div[1]/div[1]/div[2]/div[1]/ul/li[3]/a')
        # href.click()
        # time.sleep(get_random_interval(CONFIG['STEP_TIME']))
        
        # Wait for login form
        Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))
        
        try:
            logger.info("Clicking bounce arrow again...")
            a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
            a.click()
            time.sleep(get_random_interval(CONFIG['STEP_TIME']))
        except Exception as e:
            logger.warning(f"Could not find second bounce arrow: {e}")
            # Continue anyway
        
        # Perform the actual login
        do_login_action()
        return True

            
    except Exception as e:
        logger.error(f"Login failed with error: {e}")
        if CONFIG['DEBUG_MODE']:
            logger.debug(f"Detailed error: {str(e)}")
        
        try:
            if driver is not None:
                driver.save_screenshot('login_error.png')
                logger.info("Error screenshot saved as login_error.png")
                
                if CONFIG['DEBUG_MODE']:
                    logger.debug(f"Page source at error: {driver.page_source[:1000]}...")
        except:
            pass
            
        return False

def do_login_action():
    """Fill in and submit the login form."""
    try:
        logger.info("Filling in login form...")
        
        # Input email with random delay
        logger.debug("Entering email...")
        user = driver.find_element(By.ID, 'user_email')
        user.clear()
        for c in CONFIG['USERNAME']:
            user.send_keys(c)
            time.sleep(random.uniform(0.05, 0.15))  # Human-like typing
        time.sleep(random.uniform(1, 3))
        
        # Input password with random delay
        logger.debug("Entering password...")
        pw = driver.find_element(By.ID, 'user_password')
        pw.clear()
        for c in CONFIG['PASSWORD']:
            pw.send_keys(c)
            time.sleep(random.uniform(0.05, 0.15))  # Human-like typing
        time.sleep(random.uniform(1, 3))
        
        # Click privacy checkbox
        logger.debug("Clicking privacy checkbox...")
        box = driver.find_element(By.CLASS_NAME, 'icheckbox')
        box.click()
        time.sleep(random.uniform(1, 3))
        
        # Click signin button
        logger.debug("Clicking submit button...")
        btn = driver.find_element(By.NAME, 'commit')
        btn.click()
        time.sleep(random.uniform(2, 4))
        
        # Wait for successful login indicator
        try:
            Wait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE)))
            logger.info("Login form submitted successfully")
            return True
        except Exception as e:
            logger.error(f"Timeout waiting for login confirmation: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error during login form submission: {e}")
        if CONFIG['DEBUG_MODE']:
            logger.debug(f"Page source at login error: {driver.page_source[:1000]}...")
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

def is_logged_in():
    content = driver.page_source

    if(content.find("error") != -1):
        return False
    return True

def get_date():
    """Get available appointment dates."""
    global driver
    
    try:
        logger.info(f"Checking for available dates: {DATE_URL}")
        
        # Navigate to the date URL
        driver.get(DATE_URL)
        
        # Check if we're still logged in
        if not is_logged_in():
            logger.warning("Session expired, logging in again...")
            login()
            return get_date()
        
        # Get the JSON response
        content = driver.find_element(By.TAG_NAME, 'pre').text
        
        # Parse the dates
        dates = json.loads(content)
        logger.info(f"Found {len(dates)} available dates")
        
        return dates
        
    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        
        try:
            if driver is not None:
                driver.save_screenshot('date_error.png')
        except:
            pass
            
        return []

def get_time(date):
    """Get available appointment times for a given date."""
    try:
        logger.info(f"Getting available times for date: {date}")
        
        # Format the URL with the date
        time_url = TIME_URL % date
        
        # Navigate to the time URL
        driver.get(time_url)
        
        # Get the JSON response
        content = driver.find_element(By.TAG_NAME, 'pre').text
        
        # Parse the times
        data = json.loads(content)
        times = data.get("available_times", [])
        
        if not times:
            logger.warning(f"No available times found for date {date}")
            return None
            
        # Get the last time slot (usually latest in the day)
        time = times[-1]
        logger.info(f"Selected time slot: {date} {time}")
        
        return time
        
    except Exception as e:
        logger.error(f"Error getting available times: {e}")
        return None

def reschedule(date):
    """Reschedule appointment to the given date."""
    global EXIT
    
    try:
        logger.info(f"Starting reschedule process for date: {date}")
        
        # Get an available time slot
        time = get_time(date)
        if not time:
            logger.error("Could not get time slot, aborting reschedule")
            return False
        
        # Navigate to the appointment page
        driver.get(APPOINTMENT_URL)
        
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
                "appointments[consulate_appointment][time]": time,
            }
            
            # Get cookies for the request
            headers = {
                "User-Agent": driver.execute_script("return navigator.userAgent;"),
                "Referer": APPOINTMENT_URL,
                "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
            }
            
            # Submit the reschedule request
            logger.info("Submitting reschedule request...")
            response = driver.request('POST', APPOINTMENT_URL, data=data, headers=headers)
            
            # Check if reschedule was successful
            if 'Successfully Scheduled' in response.text:
                msg = f"✅ *Appointment Rescheduled!*\n\nNew appointment date: *{date}*\nTime: *{time}*"
                send_telegram_notification(msg)
                
                # Take a screenshot of the confirmation
                try:
                    driver.save_screenshot('reschedule_success.png')
                    logger.info("Saved confirmation screenshot")
                except:
                    pass
                    
                EXIT = True
                return True
            else:
                msg = f"❌ *Reschedule Failed*\n\nAttempted date: *{date}*\nTime: *{time}*\n\nThe slot may have been taken by someone else."
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
            
            update.message.reply_text(
                f"📊 *Bot Status*\n\n"
                f"Version: {VERSION}\n"
                f"Host: {hostname}\n"
                f"Uptime: {uptime}\n"
                f"Current appointment: {CONFIG['MY_SCHEDULE_DATE']}\n"
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
        
        # Ensure driver is active
        if driver is None or not is_driver_active():
            setup_driver()
            login()
        
        # Get available dates
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
    global driver, EXIT
    
    try:
        # Print startup banner
        print(f"=" * 60)
        print(f"  US Visa Slot Checker Bot v{VERSION}")
        print(f"  Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=" * 60)
        
        # Initialize WebDriver
        driver = setup_driver()
        if driver is None:
            raise Exception("Failed to initialize WebDriver")
        
        # Log in to the website
        if not login():
            raise Exception("Initial login failed")
        
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