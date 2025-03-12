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
from constants import DEFAULT_CHECK_INTERVAL
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
list_of_dates = set()
list_of_date_times = map()

# Dictionary to track active loop tasks
active_loops = {}

# Dictionary to track active visa check tasks
active_visa_checks = {}

# Global variable to store chat ID
stored_chat_id = None

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
async def check_visa_appointments(bot, chat_id, user_id, interval=300):
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
            await bot.send_message(
                chat_id=chat_id,
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
        
        # Notify user
        await bot.send_message(
            chat_id=chat_id,
            text=f"Starting visa appointment checks every {interval} seconds. I'll notify you when appointments become available."
        )
        
        last_available_date = None
        counter = 1
        
        while user_id in active_visa_checks:
            logger.info(f"Check #{counter} for user {user_id}")
            
            # Login if needed
            if not checker.is_logged_in:
                if not checker.login():
                    await bot.send_message(
                        chat_id=chat_id,
                        text="Failed to log in to the visa appointment system. Please check your credentials."
                    )
                    break
            
            # Check for appointments
            dates = checker.get_available_dates()

            # Store the earliest available date and time of check in global variables
            if dates and len(dates) > 0:
                last_available_pool_date = dates[0].get('date')
                logger.info(f"Found available date: {last_available_pool_date}")
            else:
                last_available_pool_date = None
                logger.info("No available dates found")
                
            last_pool_check = datetime.datetime.now()
            logger.info(f"Updated last_pool_check to {last_pool_check}")
            
            # Get earliest appointment date for comparison
            earlier_appointment = dates[0].get('date') if dates and len(dates) > 0 else None

            # If appointments became available and weren't before, send notification
            if dates and (not last_available_date or (last_available_date != earlier_appointment)):
                annual_date = datetime.datetime.now() + datetime.timedelta(days=365)
                iso_string = annual_date.strftime("%Y-%m-%d")
                if is_earlier_date(last_available_pool_date, iso_string):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🔔 NEW VISA APPOINTMENTS AVAILABLE! 🔔\nCheck the system now to book your appointment!"
                    )

                # add extra check to see if the appointment is 6 months from now second arg should be in iso format
                future_date = datetime.datetime.now() + datetime.timedelta(days=180)
                iso_string = future_date.strftime("%Y-%m-%d")
                if is_earlier_date(last_available_pool_date, iso_string):
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🔔 🔔 🔔 🔔 🔔 🔔 🔔 6 MONTHS FROM NOW 🔔 🔔 🔔 🔔 🔔 🔔 🔔 "
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🔔 🔔 🔔 🔔 🔔 🔔 🔔 "
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🔔 🔔 🔔 🔔 🔔 🔔 🔔 "
                    )
                
                # If facility ID is provided, get and send available dates
                if dates:
                    # date_info = []
                    # for date in dates[:1]:  # Get first 5 dates
                    #     date_info.append(f"{date.get('date')} - Business day: }")

                    # await bot.send_message(
                    #     chat_id=chat_id,
                    #     text=f"Available dates:\n" + "\n".join(date_info)
                    # )
                    
                    # Get times for the first available date
                    first_date = dates[0].get('date')
                    list_of_dates.add(first_date)
                    times = checker.get_available_times(first_date)
                    if times:
                        if first_date not in list_of_dates:
                            list_of_date_times.append(first_date, times)
                            # await bot.send_message(
                            #     chat_id=chat_id,
                            #     text=f"Available times for {first_date}:\n" + "\n".join(times[:5])
                            # )
            
            # If appointments were available but aren't anymore, send notification
            elif not earlier_appointment and last_available_date:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Visa appointments are no longer available."
                )
            
            # Update last state
            last_available_date = earlier_appointment
            
            # Check status
            if counter % 10 == 0:
                status = f"Available: {earlier_appointment}" if earlier_appointment else "Not available"
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Status update (check #{counter}): Visa appointments: {status}"
                )
            
            counter += 1
            
            # Wait for the specified interval
            random_interval = get_random_interval(interval)

            logger.info(f"next check in {random_interval} seconds")
            # prin in green color
            print(f"\033[32mnext check in {random_interval} seconds\033[0m")
            await asyncio.sleep(random_interval)
    except asyncio.CancelledError:
        # Task was cancelled, clean exit
        await bot.send_message(
            chat_id=chat_id,
            text="Visa appointment checks have been stopped."
        )
    except Exception as e:
        logger.error(f"Error in visa appointment checks: {str(e)}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"An error occurred while checking visa appointments: {str(e)}"
        )

# Define the start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command and store chat ID globally."""
    global stored_chat_id
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Store the chat ID globally
    stored_chat_id = chat_id
    
    # Log the stored chat ID
    logger.info(f"Chat ID {chat_id} stored globally")
    
    # Display stored chat ID to the user
    await update.message.reply_text(f"Your chat ID ({chat_id}) has been stored. Use /startvisa to begin visa checks.")
    
    # Regular start command menu
    await send_menu(update, context)

# Helper function to send the menu
async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the interactive menu."""
    keyboard = [
        [InlineKeyboardButton("Start Loop Messages", callback_data="start_loop")],
        [InlineKeyboardButton("Start Visa Checks", callback_data="start_visa")],
        [InlineKeyboardButton("Stop Visa Checks", callback_data="stop_visa")],
        [InlineKeyboardButton("Status", callback_data="status")],
        [InlineKeyboardButton("Last Pool Check", callback_data="last_pool_check")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'Choose an option:',
        reply_markup=reply_markup
    )

# Define a separate command for starting visa checks
async def start_visa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start visa appointment checks using the stored chat ID."""
    global stored_chat_id
    
    user_id = update.effective_user.id
    
    # Check if we have a stored chat ID
    if stored_chat_id is None:
        stored_chat_id = update.effective_chat.id
        logger.info(f"Chat ID {stored_chat_id} stored during visa check")
    
    # Parse interval if provided
    interval = get_random_interval(DEFAULT_CHECK_INTERVAL)
    
    # Cancel any existing visa check for this user
    if user_id in active_visa_checks:
        active_visa_checks[user_id].cancel()
        await update.message.reply_text('Stopping previous visa check and starting a new one...')
    
    # Start a background task for this user
    task = asyncio.create_task(check_visa_appointments(context.bot, stored_chat_id, user_id, interval))
    active_visa_checks[user_id] = task
    
    await update.message.reply_text(
        f'Starting visa appointment checks every {interval} seconds.\n'
        f'Using chat ID: {stored_chat_id}\n'
        f'Send /stopvisa to stop the checks.'
    )

# Update button callback function for the new structure
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
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
        global stored_chat_id
        
        # Store chat ID if not already stored
        if stored_chat_id is None:
            stored_chat_id = chat_id
        
        # Cancel any existing visa check for this user
        if user_id in active_visa_checks:
            active_visa_checks[user_id].cancel()
            await query.edit_message_text('Stopping previous visa check and starting a new one...')
        
        # Parse interval
        interval = get_random_interval(DEFAULT_CHECK_INTERVAL)
        
        # Start a background task for this user
        task = asyncio.create_task(check_visa_appointments(context.bot, stored_chat_id, user_id, interval))
        active_visa_checks[user_id] = task
        
        await query.edit_message_text(
            f'Starting visa appointment checks every {interval} seconds.\n'
            f'Using chat ID: {stored_chat_id}\n'
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
        
        await query.edit_message_text("\n".join(status_message))
    
    elif query.data == "last_pool_check":
        global last_available_pool_date, last_pool_check, list_of_dates, list_of_date_times
        # create message with dates and times of list_of_date_times
        message = f"Last pool check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}"
        for date, times in list_of_date_times:
            message += f"{date}: {times}\n"
        if last_pool_check:
            if last_available_pool_date:
                message += f"\nEarliest available date: {last_available_pool_date}"
            else:
                message += "\nNo available appointments found."
        else:
            message = "No pool checks have been performed yet."
        
        await query.edit_message_text(message)
    
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
    
    await update.message.reply_text("\n".join(status_message))

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
    global last_available_pool_date, last_pool_check
    
    if last_pool_check:
        message = f"Last pool check: {last_pool_check.strftime('%Y-%m-%d %H:%M:%S')}"
        if last_available_pool_date:
            message += f"\nEarliest available date: {last_available_pool_date}"
        else:
            message += "\nNo available appointments found."
    else:
        message = "No pool checks have been performed yet."
    
    await update.message.reply_text(message)

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
        application.add_handler(CommandHandler("start_visa", start_visa))  # Fixed command
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("stop_visa", stop_visa))    # Fixed command
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("last_pool", last_pool))
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Start the Bot
        logger.info("Bot is starting...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Failed to start the bot: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    main()