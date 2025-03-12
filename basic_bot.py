import datetime
import logging
import os
import sys
import requests
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Global variables for tracking appointment status
last_available_pool_date = None
last_pool_check = None
list_of_dates = set()  # Use a set to store unique dates
list_of_date_times = {}  # Use a dictionary to store date-time pairs

# Dictionary to track active loop tasks
active_loops = {}

# Dictionary to track active visa check tasks
active_visa_checks = {}

# Dictionary to store subscribed users and their chat IDs
subscribed_users = {}  # Format: {user_id: chat_id}

# Helper function to send messages to all subscribers
async def send_to_all_subscribers(bot, message):
    """Send a message to all subscribed users."""
    for user_id, chat_id in subscribed_users.items():
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message
            )
            logger.info(f"Notification sent to user {user_id} (chat ID: {chat_id})")
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {str(e)}")

# Function to send messages in a loop
async def send_loop_messages(bot, chat_id, user_id):
    """Send messages every 3 seconds until stopped."""
    try:
        counter = 1
        while user_id in active_loops:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Loop message #{counter}"
            )
            counter += 1
            
            # Wait for 3 seconds
            await asyncio.sleep(3)
    except asyncio.CancelledError:
        # Task was cancelled, clean exit
        await bot.send_message(
            chat_id=chat_id,
            text="Loop messages have been stopped."
        )
    except Exception as e:
        logger.error(f"Error in loop messages: {str(e)}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"An error occurred in the loop: {str(e)}"
        )

# Function to check visa appointments regularly
async def check_visa_appointments(bot, user_id, interval=300):
    """Check for visa appointments at regular intervals."""
    global last_available_pool_date, last_pool_check, list_of_dates, list_of_date_times  # Explicitly declare globals
    
    try:
        # Get visa appointment configuration from environment variables
        email = os.getenv('VISA_EMAIL')
        password = os.getenv('VISA_PASSWORD')
        schedule_id = os.getenv('SCHEDULE_ID')
        country_code = os.getenv('COUNTRY_CODE', 'en-ca')
        visa_type = os.getenv('VISA_TYPE', 'niv')
        facility_id = os.getenv('FACILITY_ID')
        
        # Validate required configuration
        if not all([email, password, schedule_id]):
            # Send message to the user who initiated the check
            if user_id in subscribed_users:
                await bot.send_message(
                    chat_id=subscribed_users[user_id],
                    text="Missing visa appointment configuration. Please set VISA_EMAIL, VISA_PASSWORD, and SCHEDULE_ID in .env file."
                )
            return
        
        # Initialize checker
        checker = VisaAppointmentChecker(
            email,
            password,
            schedule_id,
            country_code,
            visa_type,
            facility_id
        )
        
        # Notify the user who initiated the check
        if user_id in subscribed_users:
            await bot.send_message(
                chat_id=subscribed_users[user_id],
                text=f"Starting visa appointment checks every {interval} seconds. I'll notify all {len(subscribed_users)} subscribed users when appointments become available."
            )
        
        last_available_date = None
        counter = 1
        
        while user_id in active_visa_checks:
            logger.info(f"Check #{counter} for user {user_id}")
            
            # Login if needed
            if not checker.is_logged_in:
                if not checker.login():
                    # Send failure message only to the initiating user
                    if user_id in subscribed_users:
                        await bot.send_message(
                            chat_id=subscribed_users[user_id],
                            text="Failed to log in to the visa appointment system. Please check your credentials."
                        )
                    break
            
            # Check for appointments
            dates = checker.get_available_dates()

            # Store the earliest available date and time of check in global variables
            current_earliest_date = dates[0].get('date') if dates and len(dates) > 0 else None
            if current_earliest_date:
                last_available_pool_date = current_earliest_date
                logger.info(f"Found available date: {last_available_pool_date}")
            else:
                last_available_pool_date = None
                logger.info("No available dates found")
                
            last_pool_check = datetime.datetime.now()
            logger.info(f"Updated last_pool_check to {last_pool_check}")
            
            # Case 1: New appointments became available (none were available before)
            if current_earliest_date and last_available_date is None:
                # Prepare a single consolidated notification
                notification_parts = [
                    "🔔 NEW VISA APPOINTMENTS AVAILABLE! 🔔",
                    f"📅 Earliest available date: {current_earliest_date}"
                ]
                
                # Check if appointment is within the next 6 months
                try:
                    appointment_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                    future_date = datetime.datetime.now() + datetime.timedelta(days=180)
                    days_until = (appointment_date - datetime.datetime.now()).days
                    
                    notification_parts.append(f"⏳ Days until appointment: {days_until}")
                    
                    if appointment_date < future_date:
                        notification_parts.append("🚨 URGENT: Appointment available within next 6 months! 🚨")
                except Exception as e:
                    logger.error(f"Error comparing dates: {e}")
                
                # Get and log appointment details
                if dates:
                    # Get times for the first available date
                    first_date = dates[0].get('date')
                    times = checker.get_available_times(first_date)
                    
                    # Store the date in our set of unique dates
                    list_of_dates.add(first_date)
                    
                    # Only store the date-time pair if we haven't stored it before
                    if first_date not in list_of_date_times and times:
                        list_of_date_times[first_date] = times
                    
                    # Add time slot info to notification
                    time_info = f"Available time slots: {len(times)}" if times else "No specific times available"
                    notification_parts.append(time_info)
                    
                    # Add action prompt
                    notification_parts.append("\nPlease check the system now to book your appointment!")
                
                # Send a single consolidated notification to all subscribed users
                await send_to_all_subscribers(bot, "\n\n".join(notification_parts))
            
            # Case 2: Earlier appointment became available (better than what was available before)
            elif current_earliest_date and last_available_date:
                # Convert string dates to datetime objects for proper comparison
                try:
                    current_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                    last_date = datetime.datetime.strptime(last_available_date, '%Y-%m-%d')
                    
                    # Check if current date is earlier than the last known date
                    if current_date < last_date:
                        # Prepare a single consolidated notification for earlier appointment
                        notification_parts = [
                            "🔔 EARLIER APPOINTMENT AVAILABLE! 🔔",
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
                        
                        # Get and store new appointment details
                        if dates:
                            first_date = dates[0].get('date')
                            times = checker.get_available_times(first_date)
                            
                            list_of_dates.add(first_date)
                            if first_date not in list_of_date_times and times:
                                list_of_date_times[first_date] = times
                                
                            # Add time slot info
                            time_info = f"Available time slots: {len(times)}" if times else "No specific times available"
                            notification_parts.append(time_info)
                            
                            # Add action prompt
                            notification_parts.append("\nPlease check the system now to book your appointment!")
                        
                        # Send consolidated notification to all subscribers
                        await send_to_all_subscribers(bot, "\n\n".join(notification_parts))
                except Exception as e:
                    logger.error(f"Error comparing appointment dates: {e}")
            
            # Case 3: Appointments were available but aren't anymore
            elif not current_earliest_date and last_available_date:
                notification_parts = [
                    "⚠️ ALERT: Visa appointments are no longer available",
                    f"📆 Previously available date: {last_available_date}",
                    f"🕒 Last check time: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}",
                    "\nThe system will continue checking for new appointments."
                ]
                
                await send_to_all_subscribers(bot, "\n\n".join(notification_parts))
            
            # Update last state for next comparison
            last_available_date = current_earliest_date
            
            # Check status
            if counter % 10 == 0:
                status = f"Available: {current_earliest_date}" if current_earliest_date else "Not available"
                
                # Create a more informative status message
                status_message = [f"Status update (check #{counter}):"]
                status_message.append(f"Visa appointments: {status}")
                
                if current_earliest_date:
                    # Calculate days difference for better context
                    appointment_date = datetime.datetime.strptime(current_earliest_date, '%Y-%m-%d')
                    today = datetime.datetime.now()
                    days_away = (appointment_date - today).days
                    
                    status_message.append(f"Days until appointment: {days_away}")
                    
                    # Add information about time slots if available
                    if current_earliest_date in list_of_date_times:
                        times_count = len(list_of_date_times[current_earliest_date])
                        status_message.append(f"Time slots available: {times_count}")
                
                # Only send status to the initiating user, not all subscribers
                if user_id in subscribed_users:
                    await bot.send_message(
                        chat_id=subscribed_users[user_id],
                        text="\n".join(status_message)
                    )
            
            counter += 1
            
            # Wait for the specified interval
            random_interval = get_random_interval(interval)

            logger.info(f"next check in {random_interval} seconds")
            # print in green color
            print(f"\033[32mnext check in {random_interval} seconds\033[0m")
            await asyncio.sleep(random_interval)
    except asyncio.CancelledError:
        # Task was cancelled, clean exit
        if user_id in subscribed_users:
            await bot.send_message(
                chat_id=subscribed_users[user_id],
                text="Visa appointment checks have been stopped."
            )
    except Exception as e:
        logger.error(f"Error in visa appointment checks: {str(e)}")
        if user_id in subscribed_users:
            await bot.send_message(
                chat_id=subscribed_users[user_id],
                text=f"An error occurred while checking visa appointments: {str(e)}"
            )

# Define the start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command and subscribe the user."""
    global subscribed_users
    
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
        f"You have been subscribed to visa appointment notifications.\n"
        f"Current subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}\n"
        f"Use /startvisa to begin visa checks or /unsubscribe to unsubscribe."
    )
    
    # Send the interactive menu
    await send_menu(update, context)

# Helper function to send the menu
async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the interactive menu."""
    user_id = update.effective_user.id
    is_subscribed = user_id in subscribed_users
    
    keyboard = [
        [InlineKeyboardButton("Start Loop Messages", callback_data="start_loop")],
        [InlineKeyboardButton("Start Visa Checks", callback_data="start_visa")],
        [InlineKeyboardButton("Stop Visa Checks", callback_data="stop_visa")],
        [InlineKeyboardButton("Check Status", callback_data="status")],
        [InlineKeyboardButton("Last Check Result", callback_data="last_pool_check")]
    ]
    
    # Add subscription management buttons
    if is_subscribed:
        keyboard.append([InlineKeyboardButton("Unsubscribe", callback_data="unsubscribe")])
    else:
        keyboard.append([InlineKeyboardButton("Subscribe", callback_data="subscribe")])
    
    # Add admin button if there are any subscribers
    if len(subscribed_users) > 0:
        keyboard.append([InlineKeyboardButton("View All Subscribers", callback_data="list_subscribers")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    subscription_status = f"✅ Subscribed ({len(subscribed_users)}/{MAX_SUBSCRIBERS} total users)" if is_subscribed else "❌ Not subscribed"
    
    await update.message.reply_text(
        f'Choose an option:\nYour subscription status: {subscription_status}',
        reply_markup=reply_markup
    )

# Define a separate command for starting visa checks
async def start_visa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start visa appointment checks for a subscribed user."""
    user_id = update.effective_user.id
    
    # Check if the user is subscribed
    if user_id not in subscribed_users:
        await update.message.reply_text(
            "You are not subscribed to receive notifications. "
            "Please use the /start command first to subscribe."
        )
        return
    
    # Parse interval if provided
    interval = get_random_interval(DEFAULT_CHECK_INTERVAL)
    
    # Cancel any existing visa check for this user
    if user_id in active_visa_checks:
        active_visa_checks[user_id].cancel()
        await update.message.reply_text('Stopping previous visa check and starting a new one...')
    
    # Start a background task for this user
    task = asyncio.create_task(check_visa_appointments(context.bot, user_id, interval))
    active_visa_checks[user_id] = task
    
    await update.message.reply_text(
        f'Starting visa appointment checks every {interval} seconds.\n'
        f'Notifications will be sent to {len(subscribed_users)} subscribed users.\n'
        f'Send /stopvisa to stop the checks.'
    )

# Update button callback function for the new structure
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    global last_available_pool_date, last_pool_check, list_of_dates, list_of_date_times
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if query.data == "start_loop":
        # Cancel any existing loop for this user
        if user_id in active_loops:
            active_loops[user_id].cancel()
            await query.edit_message_text('Stopping previous loop and starting a new one...')
        
        # Start a background task for this user
        task = asyncio.create_task(send_loop_messages(context.bot, chat_id, user_id))
        active_loops[user_id] = task
        
        await query.edit_message_text('Starting loop messages every 3 seconds. Send /stop to stop the loop.')
    
    elif query.data == "start_visa":
        # Check if the user is subscribed
        if user_id not in subscribed_users:
            await query.edit_message_text(
                "You need to be subscribed to use this feature.\n"
                "Please use the /start command first to subscribe."
            )
            return
            
        # Cancel any existing visa check for this user
        if user_id in active_visa_checks:
            active_visa_checks[user_id].cancel()
            await query.edit_message_text('Stopping previous visa check and starting a new one...')
        
        # Parse interval
        interval = get_random_interval(DEFAULT_CHECK_INTERVAL)
        
        # Start a background task for this user
        task = asyncio.create_task(check_visa_appointments(context.bot, user_id, interval))
        active_visa_checks[user_id] = task
        
        await query.edit_message_text(
            f'Starting visa appointment checks every {interval} seconds.\n'
            f'Notifications will be sent to {len(subscribed_users)} subscribed users.\n'
            f'Send /stopvisa to stop the checks.'
        )
    
    elif query.data == "stop_visa":
        if user_id in active_visa_checks:
            active_visa_checks[user_id].cancel()
            del active_visa_checks[user_id]
            await query.edit_message_text('Visa checks stopped.')
        else:
            await query.edit_message_text('No active visa checks to stop.')
    
    elif query.data == "status":
        # Create status message
        status_message = []
        
        if user_id in active_loops:
            status_message.append("✅ Loop messages: Active")
        else:
            status_message.append("❌ Loop messages: Inactive")
        
        if user_id in active_visa_checks:
            status_message.append("✅ Visa checks: Active")
        else:
            status_message.append("❌ Visa checks: Inactive")
        
        # Check if user is subscribed
        if user_id in subscribed_users:
            status_message.append(f"✅ Subscription: Active (1 of {len(subscribed_users)}/{MAX_SUBSCRIBERS} users)")
        else:
            status_message.append("❌ Subscription: Not subscribed")
            status_message.append("Use /start to subscribe for notifications.")
        
        # Add last pool check information
        if last_pool_check:
            status_message.append(f"\nLast check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}")
            if last_available_pool_date:
                status_message.append(f"Earliest available date: {last_available_pool_date}")
            else:
                status_message.append("No available appointments found.")
        else:
            status_message.append("\nNo checks performed yet.")
        
        # Add subscriber count
        status_message.append(f"\nTotal subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}")
        
        await query.edit_message_text("\n".join(status_message))
    
    elif query.data == "last_pool_check":
        # Create message with dates and times from list_of_date_times dictionary
        if last_pool_check:
            message = f"Last pool check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            if list_of_date_times:
                message += "Stored appointment dates and times:\n"
                for date, times in list_of_date_times.items():
                    message += f"Date: {date}\n"
                    # Display up to 5 times for each date to avoid very long messages
                    for i, time in enumerate(times[:5]):
                        message += f"  Time {i+1}: {time}\n"
                    if len(times) > 5:
                        message += f"  ... and {len(times) - 5} more times\n"
            else:
                message += "No appointment dates/times stored yet.\n"
                
            if last_available_pool_date:
                message += f"\nEarliest available date: {last_available_pool_date}"
            else:
                message += "\nNo available appointments found."
        else:
            message = "No pool checks have been performed yet."
        
        await query.edit_message_text(message)
    
    elif query.data == "unsubscribe":
        if user_id in subscribed_users:
            # Remove the user from subscriptions
            del subscribed_users[user_id]
            
            # Also stop any active visa checks for this user
            if user_id in active_visa_checks:
                active_visa_checks[user_id].cancel()
                del active_visa_checks[user_id]
            
            logger.info(f"User {user_id} unsubscribed. Remaining subscribers: {len(subscribed_users)}")
            
            await query.edit_message_text(
                "You have been unsubscribed from visa appointment notifications.\n"
                "You will no longer receive alerts.\n"
                "You can subscribe again anytime using /start."
            )
        else:
            await query.edit_message_text(
                "You are not currently subscribed to notifications."
            )
    
    elif query.data == "list_subscribers":
        # Add an admin check here if needed
        
        if not subscribed_users:
            await query.edit_message_text("No users are currently subscribed.")
            return
        
        message = [f"Current subscribers ({len(subscribed_users)}/{MAX_SUBSCRIBERS}):"]
        
        for i, (user_id, chat_id) in enumerate(subscribed_users.items(), 1):
            message.append(f"{i}. User ID: {user_id}, Chat ID: {chat_id}")
        
        await query.edit_message_text("\n".join(message))
    
    elif query.data == "subscribe":
        # Check if the maximum number of subscribers has been reached
        if user_id not in subscribed_users and len(subscribed_users) >= MAX_SUBSCRIBERS:
            await query.edit_message_text(
                f"Sorry, the maximum number of subscribers ({MAX_SUBSCRIBERS}) has been reached. "
                f"Please try again later or contact the bot administrator."
            )
            return
        
        # Add or update the user's subscription
        subscribed_users[user_id] = chat_id
        
        # Log the subscribed user
        logger.info(f"User {user_id} (chat ID: {chat_id}) subscribed via button. Total subscribers: {len(subscribed_users)}")
        
        # Display subscription confirmation to the user
        await query.edit_message_text(
            f"✅ You have been subscribed to visa appointment notifications.\n"
            f"Current subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}\n"
            f"Use /startvisa to begin visa checks or /unsubscribe to unsubscribe."
        )
    
    else:
        await query.edit_message_text(f'Command not found: {query.data}')

# Define a stop command to halt the loop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the loop messages."""
    user_id = update.effective_user.id
    
    if user_id in active_loops:
        # Get the task
        task = active_loops[user_id]
        
        # Cancel the task
        task.cancel()
        
        # Remove from active loops
        del active_loops[user_id]
        
        await update.message.reply_text('Stopping the loop messages.')
    else:
        await update.message.reply_text('No active loop to stop.')

# Define a stop command to halt the visa checks
async def stop_visa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the visa appointment checks."""
    user_id = update.effective_user.id
    
    if user_id in active_visa_checks:
        # Get the task
        task = active_visa_checks[user_id]
        
        # Cancel the task
        task.cancel()
        
        # Remove from active visa checks
        del active_visa_checks[user_id]
        
        await update.message.reply_text('Stopping the visa appointment checks.')
    else:
        await update.message.reply_text('No active visa checks to stop.')

# Define a status command to check current status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current status of all checks."""
    user_id = update.effective_user.id
    
    status_message = []
    
    # Check if user is subscribed
    if user_id in subscribed_users:
        status_message.append(f"✅ Subscription: Active (1 of {len(subscribed_users)}/{MAX_SUBSCRIBERS} users)")
    else:
        status_message.append("❌ Subscription: Not subscribed")
        status_message.append("Use /start to subscribe for notifications.")
    
    # Check active services
    if user_id in active_loops:
        status_message.append("✅ Loop messages: Active")
    else:
        status_message.append("❌ Loop messages: Inactive")
    
    if user_id in active_visa_checks:
        status_message.append("✅ Visa checks: Active")
    else:
        status_message.append("❌ Visa checks: Inactive")
    
    # Add last pool check information
    if last_pool_check:
        status_message.append(f"\nLast check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}")
        if last_available_pool_date:
            status_message.append(f"Earliest available date: {last_available_pool_date}")
        else:
            status_message.append("No available appointments found.")
    else:
        status_message.append("\nNo checks performed yet.")
    
    # Add subscriber count
    status_message.append(f"\nTotal subscribers: {len(subscribed_users)}/{MAX_SUBSCRIBERS}")
    
    await update.message.reply_text("\n".join(status_message))

# Add a new command to unsubscribe
async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe the user from notifications."""
    global subscribed_users
    
    user_id = update.effective_user.id
    
    if user_id in subscribed_users:
        # Remove the user from subscriptions
        del subscribed_users[user_id]
        
        # Also stop any active visa checks for this user
        if user_id in active_visa_checks:
            active_visa_checks[user_id].cancel()
            del active_visa_checks[user_id]
        
        logger.info(f"User {user_id} unsubscribed. Remaining subscribers: {len(subscribed_users)}")
        
        await update.message.reply_text(
            "You have been unsubscribed from visa appointment notifications.\n"
            "You will no longer receive alerts.\n"
            "You can subscribe again anytime using /start."
        )
    else:
        await update.message.reply_text(
            "You are not currently subscribed to notifications."
        )

# Define a command to list all current subscribers (for admin use)
async def list_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all current subscribers (admin only)."""
    # Add an admin check here if needed
    
    if not subscribed_users:
        await update.message.reply_text("No users are currently subscribed.")
        return
    
    message = [f"Current subscribers ({len(subscribed_users)}/{MAX_SUBSCRIBERS}):"]
    
    for i, (user_id, chat_id) in enumerate(subscribed_users.items(), 1):
        message.append(f"{i}. User ID: {user_id}, Chat ID: {chat_id}")
    
    await update.message.reply_text("\n".join(message))

def check_token_validity(token):
    """Verify if the token is valid by making a request to Telegram API"""
    try:
        response = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            logger.info(f"Token is valid! Bot name: {bot_info['result']['first_name']}")
            return True
        else:
            logger.error(f"Token seems invalid. Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error checking token: {str(e)}")
        return False

def check_internet_connection():
    """Check if there's a working internet connection"""
    try:
        # Try to reach Telegram's API
        response = requests.get('https://api.telegram.org', timeout=5)
        logger.info("Internet connection: OK")
        return True
    except requests.ConnectionError:
        logger.error("Internet connection: FAILED - Cannot reach Telegram API")
        return False
    except Exception as e:
        logger.error(f"Internet connection check error: {str(e)}")
        return False
    
async def last_pool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the last pool check date and time."""
    global last_available_pool_date, last_pool_check, list_of_date_times
    
    if last_pool_check:
        message = [f"🔍 Last pool check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}"]
        
        if last_available_pool_date:
            # Calculate how many days away the appointment is
            try:
                appointment_date = datetime.datetime.strptime(last_available_pool_date, '%Y-%m-%d')
                today = datetime.datetime.now()
                days_away = (appointment_date - today).days
                
                message.append(f"\n📅 Earliest available date: {last_available_pool_date} ({days_away} days from today)")
            except Exception as e:
                message.append(f"\n📅 Earliest available date: {last_available_pool_date}")
                logger.error(f"Error calculating days difference: {e}")
        else:
            message.append("\n❌ No available appointments found.")
        
        if list_of_date_times:
            message.append("\n🕒 Stored appointment dates and times:")
            
            # Sort dates chronologically for better display
            sorted_dates = sorted(list_of_date_times.keys())
            
            for date in sorted_dates:
                times = list_of_date_times[date]
                message.append(f"  Date: {date} - {len(times)} time slots available")
                
                # Display up to 3 times for each date to avoid very long messages
                for i, time in enumerate(times[:3]):
                    message.append(f"    ⏰ {time}")
                
                if len(times) > 3:
                    message.append(f"    ... and {len(times) - 3} more times")
        else:
            message.append("\n❌ No appointment dates/times stored yet.")
    else:
        message = ["No pool checks have been performed yet."]
    
    await update.message.reply_text("\n".join(message))

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the main menu."""
    await send_menu(update, context)

# Update main function to register the new command
def main():
    # Get the bot token from environment variables
    bot_token = os.getenv('TELEGRAM_TOKEN')
    
    if not bot_token:
        logger.error("Error: TELEGRAM_TOKEN not found in .env file")
        sys.exit(1)
    
    # Check internet connection
    if not check_internet_connection():
        logger.error("Please check your internet connection and try again.")
        sys.exit(1)
    
    # Verify token validity
    if not check_token_validity(bot_token):
        logger.error("Please verify your bot token and try again.")
        sys.exit(1)
    
    try:
        # Create the application with proxy settings if needed
        application_builder = ApplicationBuilder().token(bot_token)
        
        # Uncomment and modify the following line if you need to use a proxy
        # application_builder.proxy_url('socks5://proxy_address:proxy_port')
        
        application = application_builder.build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("startvisa", start_visa))
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("stopvisa", stop_visa))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("lastpool", last_pool))
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(CommandHandler("unsubscribe", unsubscribe))
        application.add_handler(CommandHandler("subscribe", start))
        application.add_handler(CommandHandler("listsubscribers", list_subscribers))
          # Alias for start command
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Start the Bot
        logger.info("Bot is starting...")
        logger.info(f"Maximum subscribers allowed: {MAX_SUBSCRIBERS}")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Failed to start the bot: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    main()