import datetime
import logging
import os
import sys
import requests
import asyncio
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# Import the VisaAppointmentChecker from the separate file
from checker import VisaAppointmentChecker
from constants import DEFAULT_CHECK_INTERVAL, MAX_SUBSCRIBERS
from utils import get_random_interval, is_earlier_date

# Load environment variables
load_dotenv()

# Set up logging with more details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Admin user configuration
ADMIN_CHAT_ID = int(os.getenv('CHAT_ID', '434679558'))  # Read from .env, fallback to default
logger.info(f"Admin user ID configured: {ADMIN_CHAT_ID}")

# Global variables for tracking appointment status
appointment_data = {
    'last_available_date': None,
    'last_check_time': None,
    'available_dates': {},  # Format: {date_str: [times]}
}

# Global checker task
global_checker_task = None
global_checker_running = False

# Dictionary to store subscribed users and their chat IDs
subscribed_users = {}  # Format: {user_id: chat_id}

# Session cache expiry (in seconds)
CHECKER_CACHE_EXPIRY = 1800  # 30 minutes
checker_last_created = 0
checker_instance = None

# Helper function to send messages to all subscribers
async def send_to_all_subscribers(bot, message, is_urgent=False):
    """Send a message to all subscribed users."""
    for user_id, chat_id in subscribed_users.items():
        try:
            # Check if this is an urgent notification (< 360 days)
            if is_urgent:
                # Split into multiple messages to create multiple notifications
                await bot.send_message(chat_id=chat_id, text="🚨 ТЕРМІНОВО! ДОСТУПНИЙ ЗАПИС! 🚨")
                await asyncio.sleep(0.5)  # Small delay between messages
                await bot.send_message(chat_id=chat_id, text=message)            
                await asyncio.sleep(0.5)  # Small delay between messages
                await bot.send_message(chat_id=chat_id, text="💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡💡")
                await asyncio.sleep(1)  # Small delay between messages
                await bot.send_message(chat_id=chat_id, text="💎💎💎💎💎 ТЕРМІНОВО! ДОСТУПНИЙ ЗАПИС! 💎💎💎💎💎")
                await asyncio.sleep(1.5)  # Small delay between messages\
                await bot.send_message(chat_id=chat_id, text="🪪🪪🪪🪪🪪🪪 ТЕРМІНОВО! ДОСТУПНИЙ ЗАПИС! 🪪🪪🪪🪪🪪🪪")
                await asyncio.sleep(1.5)  # Small delay between messages\
                await bot.send_message(chat_id=chat_id, text="🚨 ТЕРМІНОВО! ДОСТУПНИЙ ЗАПИС менше 1 року! 🚨")

            else:
                # Regular notification (potentially silent)
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    disable_notification=True  # Optional: make regular updates silent
            )
        
            logger.info(f"Message sent to user {user_id}, chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {str(e)}")

# Get a fresh checker instance or reuse an existing one if it's not expired
def get_checker_instance():
    """Get a checker instance, creating a new one if necessary based on cache expiry."""
    global checker_instance, checker_last_created
    
    current_time = time.time()
    
    # If no checker exists or the existing one is expired, create a new one
    if not checker_instance or (current_time - checker_last_created) > CHECKER_CACHE_EXPIRY:
        # Get visa appointment configuration from environment variables
        email = os.getenv('VISA_EMAIL')
        password = os.getenv('VISA_PASSWORD')
        schedule_id = os.getenv('SCHEDULE_ID')
        country_code = os.getenv('COUNTRY_CODE', 'en-ca')
        visa_type = os.getenv('VISA_TYPE', 'niv')
        facility_id = os.getenv('FACILITY_ID')
        
        # Create a new checker instance
        checker_instance = VisaAppointmentChecker(
            email,
            password,
            schedule_id,
            country_code,
            visa_type,
            facility_id
        )
        
        checker_last_created = current_time
        logger.info("Created new checker instance")
    
    return checker_instance

# Function to update appointment data and limit its size to 10 earliest dates
def update_appointment_data(dates, times=None):
    """Update the appointment data with new dates and times, limiting to 10 earliest dates."""
    global appointment_data
    
    if not dates:
        appointment_data['last_available_date'] = None
        return
    
    # Update last available date
    current_earliest_date = dates[0].get('date') if dates and len(dates) > 0 else None
    appointment_data['last_available_date'] = current_earliest_date
    appointment_data['last_check_time'] = datetime.datetime.now()
    
    # Store up to 10 dates with their times
    for date_info in dates:
        date_str = date_info.get('date')
        if date_str and times:
            appointment_data['available_dates'][date_str] = times
    
    # If we have more than 10 dates, keep only the 10 earliest
    if len(appointment_data['available_dates']) > 10:
        # Sort dates chronologically (earliest first)
        sorted_dates = sorted(appointment_data['available_dates'].keys())
        
        # Keep only the 10 earliest dates
        keep_dates = sorted_dates[:10]
        
        # Create a new dictionary with only the dates to keep
        filtered_dates = {}
        for date in keep_dates:
            filtered_dates[date] = appointment_data['available_dates'][date]
        
        # Replace the old dictionary with the filtered one
        appointment_data['available_dates'] = filtered_dates
        
        logger.info(f"Limited appointment data to 10 earliest dates.")

# Function to check visa appointments globally for all subscribers
async def global_visa_check(bot, interval=300):
    """Central function to check for visa appointments for all subscribers."""
    global global_checker_running, appointment_data
    
    try:
        # Get visa appointment configuration from environment variables
        email = os.getenv('VISA_EMAIL')
        password = os.getenv('VISA_PASSWORD')
        schedule_id = os.getenv('SCHEDULE_ID')
        
        # Validate required configuration
        if not all([email, password, schedule_id]):
            await send_to_all_subscribers(
                bot, 
                "Missing visa appointment configuration. Please set VISA_EMAIL, VISA_PASSWORD, and SCHEDULE_ID in .env file."
            )
            global_checker_running = False
            return
        
        # Notify all subscribers that checks are starting
        await send_to_all_subscribers(
            bot,
            f"Starting visa appointment checks every ~{interval} seconds. "
            f"All {len(subscribed_users)} subscribed users will be notified when appointments become available."
        )
        
        last_available_date = None
        counter = 1
        
        while global_checker_running:
            logger.info(f"Global check #{counter}")
            
            try:
                # Get a fresh checker instance if needed
                checker = get_checker_instance()
                
                # Login if needed
                if not checker.is_logged_in:
                    if not checker.login():
                        await send_to_all_subscribers(
                            bot,
                            "Failed to log in to the visa appointment system. Please check your credentials."
                        )
                        # Force a new checker instance next time
                        checker_instance = None
                        checker_last_created = 0
                        break
                
                # Check for appointments
                dates = checker.get_available_dates()
                
                # Get current earliest date
                current_earliest_date = dates[0].get('date') if dates and len(dates) > 0 else None
                
                # If we have a date, get the times
                times = None
                if current_earliest_date:
                    times = checker.get_available_times(current_earliest_date)
                
                # Update the global appointment data
                update_appointment_data(dates, times)
                
                # Case 1: New appointments became available (none were available before)
                if current_earliest_date and last_available_date is None:
                    is_urgent = False
                    # Prepare notification
                    notification_parts = [
                        "🔔 NEW VISA APPOINTMENTS AVAILABLE! 🔔",
                        f"📅 Earliest available date: {current_earliest_date}"
                    ]
                    
                    # Add additional information
                    try:
                        appointment_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                        six_months = datetime.datetime.now() + datetime.timedelta(days=180)
                        year = datetime.datetime.now() + datetime.timedelta(days=301)
                        future_date = datetime.datetime.now() + datetime.timedelta(days=180)
                        days_until = (appointment_date - datetime.datetime.now()).days
                        
                        notification_parts.append(f"⏳ Days until appointment: {days_until}")
                        
                        # can it be made different notification for less than 6 months?
                        if appointment_date < year:
                            is_urgent = True
                            notification_parts.append("🚨🚨🚨🚨🚨 URGENT: Less than 300 days! 🚨🚨🚨🚨🚨")
                        # Check if the appointment date is less than 6 months from now
                        if appointment_date < six_months:
                            notification_parts.append("🚨🚨🚨🚨🚨 URGENT: Less than 6 months! 🚨🚨🚨🚨🚨")
                    except Exception as e:
                        logger.error(f"Error comparing dates: {e}")
                    
                    # Add time info
                    if times:
                        time_info = f"Available time slots: {len(times)}"
                        notification_parts.append(time_info)
                    
                    # Add action prompt
                    notification_parts.append("\nPlease check the system now to book your appointment!")
                    
                    # Send to all subscribers
                    await send_to_all_subscribers(bot, "\n\n".join(notification_parts), is_urgent)
                
                # Case 2: Earlier appointment became available
                elif current_earliest_date and last_available_date:
                    # Compare dates
                    try:
                        current_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                        last_date = datetime.datetime.strptime(last_available_date, '%Y-%m-%d')
                        
                        if current_date < last_date:
                            # Prepare notification
                            notification_parts = [
                                "🔔🔔🔔 EARLIER APPOINTMENT AVAILABLE! 🔔🔔🔔",
                                f"📅 New earliest date: {current_earliest_date}",
                                f"📆 Previous earliest date: {last_available_date}"
                            ]
                            
                            # Add days information
                            days_until = (current_date - datetime.datetime.now()).days
                            days_diff = (last_date - current_date).days
                            notification_parts.append(f"⏳ Days until new appointment: {days_until}")
                            notification_parts.append(f"📊 Days earlier than previous: {days_diff}")
                            
                            # Check if within 6 months
                            future_date = datetime.datetime.now() + datetime.timedelta(days=180)
                            if current_date < future_date:
                                notification_parts.append("🚨 URGENT: Appointment available within next 6 months! 🚨")
                            
                            # Add time info
                            if times:
                                time_info = f"Available time slots: {len(times)}"
                                notification_parts.append(time_info)
                            
                            # Add action prompt
                            notification_parts.append("\nPlease check the system now to book your appointment!")
                            
                            # Send to all subscribers
                            await send_to_all_subscribers(bot, "\n\n".join(notification_parts))
                    except Exception as e:
                        logger.error(f"Error comparing appointment dates: {e}")
                
                # Case 3: Appointments were available but aren't anymore
                elif not current_earliest_date and last_available_date:
                    notification_parts = [
                        "⚠️ ALERT: Visa appointments are no longer available",
                        f"📆 Previously available date: {last_available_date}",
                        f"🕒 Last check time: {appointment_data['last_check_time'].strftime('%Y-%m-%d %H:%M:%S')}",
                        "\nThe system will continue checking for new appointments."
                    ]
                    
                    await send_to_all_subscribers(bot, "\n\n".join(notification_parts))
                
                # Update last state for next comparison
                last_available_date = current_earliest_date
                
                # Send periodic status updates to admin only
                if counter % 10 == 0:
                    status_message = [f"Status update (check #{counter}):"]
                    
                    if current_earliest_date:
                        status_message.append(f"✅ Appointments available! Earliest: {current_earliest_date}")
                        
                        # Calculate days difference
                        appointment_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                        today = datetime.datetime.now()
                        days_away = (appointment_date - today).days
                        
                        status_message.append(f"Days until appointment: {days_away}")
                        
                        # Add time slot info
                        if times:
                            status_message.append(f"Time slots available: {len(times)}")
                    else:
                        status_message.append("❌ No appointments available")
                    
                    # Send only to admin
                    if ADMIN_CHAT_ID in subscribed_users.values():
                        admin_user_id = [uid for uid, cid in subscribed_users.items() if cid == ADMIN_CHAT_ID][0]
                        await bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text="\n".join(status_message)
                        )
                
                counter += 1
                
                # Calculate next check interval with jitter
                random_interval = get_random_interval(interval)
                logger.info(f"Next check in {random_interval} seconds")
                print(f"\033[32mNext check in {random_interval} seconds\033[0m")
                
                # Sleep before next check
                await asyncio.sleep(random_interval)
            
            except Exception as e:
                logger.error(f"Error during visa check cycle: {str(e)}")
                # Wait a bit before retry
                await asyncio.sleep(30)
                # Force a new checker instance next time
                checker_instance = None
                checker_last_created = 0
    
    except asyncio.CancelledError:
        # Task was cancelled, clean exit
        global_checker_running = False
        await send_to_all_subscribers(bot, "Visa appointment checks have been stopped.")
    except Exception as e:
        global_checker_running = False
        logger.error(f"Error in global visa checks: {str(e)}")
        await send_to_all_subscribers(bot, f"An error occurred in the visa check system: {str(e)}")

# Define the start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command - subscribe the user and start visa checks if not running."""
    global subscribed_users, global_checker_task, global_checker_running
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if the maximum number of subscribers has been reached
    if user_id not in subscribed_users and len(subscribed_users) >= MAX_SUBSCRIBERS:
        await update.message.reply_text(
            f"Sorry, the maximum number of subscribers ({MAX_SUBSCRIBERS}) has been reached. "
            f"Please try again later or contact the bot administrator."
        )
        return
    
    # Add or update the user's subscription
    subscribed_users[user_id] = chat_id
    
    # Log the subscribed user
    logger.info(f"User {user_id} (chat ID: {chat_id}) subscribed. Total subscribers: {len(subscribed_users)}")
    
    # Display subscription confirmation to the user
    await update.message.reply_text(
        f"Welcome to Visa Appointment Checker! You've been subscribed to notifications.\n"
        f"Current subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}"
    )
    
    # Start visa checks if not already running
    if not global_checker_running or not global_checker_task or global_checker_task.done():
        # Parse interval
        interval = get_random_interval(DEFAULT_CHECK_INTERVAL)
        
        # Set the flag and start the global checker task
        global_checker_running = True
        global_checker_task = asyncio.create_task(global_visa_check(context.bot, interval))
        
        await update.message.reply_text(
            f'Starting visa appointment checks every ~{interval} seconds.\n'
            f'Notifications will be sent to all {len(subscribed_users)} subscribed users.\n'
            f'Use /stop to stop the checks or /last_pool to see the 10 earliest appointments.'
        )
    else:
        await update.message.reply_text(
            'Visa appointment checks are already running.\n'
            'Use /last_pool to see the 10 earliest appointments or /stop to stop the checks.'
        )

# Stop command to halt the visa checks
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the global visa appointment checks."""
    global global_checker_task, global_checker_running
    
    if global_checker_running and global_checker_task and not global_checker_task.done():
        global_checker_running = False
        global_checker_task.cancel()
        
        await update.message.reply_text('✅ Visa appointment checks have been stopped.')
    else:
        await update.message.reply_text('❌ No active visa checks to stop.')

# Command to show the 10 earliest appointments
async def last_pool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the 10 earliest appointments."""
    global appointment_data
    
    if appointment_data['last_check_time']:
        message = [f"🔍 Last check: {appointment_data['last_check_time'].strftime('%Y-%m-%d %H:%M:%S')}"]
        
        if appointment_data['last_available_date']:
            # Calculate how many days away the appointment is
            try:
                appointment_date = datetime.datetime.strptime(appointment_data['last_available_date'], '%Y-%m-%d')
                today = datetime.datetime.now()
                days_away = (appointment_date - today).days
                
                message.append(f"\n📅 Earliest available date: {appointment_data['last_available_date']} ({days_away} days from today)")
            except Exception as e:
                message.append(f"\n📅 Earliest available date: {appointment_data['last_available_date']}")
                logger.error(f"Error calculating days difference: {e}")
        else:
            message.append("\n❌ No available appointments found.")
        
        if appointment_data['available_dates']:
            message.append("\n🗓️ 10 EARLIEST APPOINTMENTS:")
            
            # Sort dates chronologically
            sorted_dates = sorted(appointment_data['available_dates'].keys())
            
            for i, date in enumerate(sorted_dates[:10], 1):
                times = appointment_data['available_dates'][date]
                
                # Try to calculate days until appointment
                try:
                    appointment_date = datetime.datetime.strptime(date, '%Y-%m-%d')
                    today = datetime.datetime.now()
                    days_away = (appointment_date - today).days
                    message.append(f"  {i}. 📆 {date} ({days_away} days) - {len(times)} time slots")
                except Exception as e:
                    message.append(f"  {i}. 📆 {date} - {len(times)} time slots")
                
                # Display up to 3 times for each date
                for j, time in enumerate(times[:3]):
                    message.append(f"     ⏰ {time}")
                
                if len(times) > 3:
                    message.append(f"     ... and {len(times) - 3} more times")
        else:
            message.append("\n❌ No appointment dates/times available.")
        
        # Add bot status
        message.append("\n🤖 BOT STATUS:")
        if global_checker_running and global_checker_task and not global_checker_task.done():
            message.append("✅ Visa checks: Active")
        else:
            message.append("⏹️ Visa checks: Stopped")
        message.append(f"👥 Total subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}")
    else:
        message = [
            "No checks have been performed yet.",
            "\n🤖 BOT STATUS:",
            "⏹️ Visa checks: Not started" if not global_checker_running else "✅ Visa checks: Active",
            f"👥 Total subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}"
        ]
    
    await update.message.reply_text("\n".join(message))

def main():
    """Start the bot."""
    # Get the bot token
    bot_token = os.getenv('TELEGRAM_TOKEN')
    
    if not bot_token:
        logger.error("Error: TELEGRAM_TOKEN not found in .env file")
        sys.exit(1)
    
    try:
        # Create the application
        application_builder = ApplicationBuilder().token(bot_token)
        application = application_builder.build()
        
        # Add only the three essential command handlers
        application.add_handler(CommandHandler("start", start))  # Subscribe + start checks
        application.add_handler(CommandHandler("stop", stop))    # Stop checks
        application.add_handler(CommandHandler("last_pool", last_pool))  # Show 10 earliest appointments
        
        # Start the Bot
        logger.info("Bot is starting with just 3 commands: /start, /stop, /last_pool")
        logger.info(f"Maximum subscribers allowed: {MAX_SUBSCRIBERS}")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Failed to start the bot: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    main()