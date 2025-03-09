import logging
import os
import sys
import requests
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, filters

# Import the VisaAppointmentChecker from the separate file
from checker import VisaAppointmentChecker

# Load environment variables
load_dotenv()

# Set up logging with more details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionary to track active loop tasks
active_loops = {}

# Dictionary to track active visa check tasks
active_visa_checks = {}

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
        
        last_available = False
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
            has_appointments = checker.check_appointment_availability()
            
            # If appointments became available and weren't before, send notification
            if has_appointments and not last_available:
                await bot.send_message(
                    chat_id=chat_id,
                    text="🔔 VISA APPOINTMENTS AVAILABLE! 🔔\nCheck the system now to book your appointment!"
                )
                
                # If facility ID is provided, get and send available dates
                if checker.facility_id:
                    dates = checker.get_available_dates()
                    if dates:
                        date_info = []
                        for date in dates[:5]:  # Get first 5 dates
                            date_info.append(f"{date.get('date')} - Business day: {date.get('business_day')}")
                        
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"Available dates:\n" + "\n".join(date_info)
                        )
                        
                        # Get times for the first available date
                        first_date = dates[0].get('date')
                        times = checker.get_available_times(first_date)
                        if times:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"Available times for {first_date}:\n" + "\n".join(times[:5])
                            )
            
            # If appointments were available but aren't anymore, send notification
            elif not has_appointments and last_available:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Visa appointments are no longer available."
                )
            
            # Update last state
            last_available = has_appointments
            
            # Check status
            if counter % 10 == 0:
                status = "Available" if has_appointments else "Not available"
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Status update (check #{counter}): Visa appointments: {status}"
                )
            
            counter += 1
            
            # Wait for the specified interval
            await asyncio.sleep(interval)
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

# Global variable to store chat ID
stored_chat_id = None

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
    keyboard = [
        [InlineKeyboardButton("Start Loop Messages", callback_data="start_loop")],
        [InlineKeyboardButton("Start Visa Checks", callback_data="start_visa")]
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
    interval = 300  # Default 5 minutes
    if context.args and context.args[0].isdigit():
        interval = int(context.args[0])
    
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
        
        # Start a background task for this user
        task = asyncio.create_task(check_visa_appointments(context.bot, stored_chat_id, user_id))
        active_visa_checks[user_id] = task
        
        await query.edit_message_text(
            f'Starting visa appointment checks.\n'
            f'Using chat ID: {stored_chat_id}\n'
            f'Send /stopvisa to stop the checks.'
        )


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
        application.add_handler(CommandHandler("start_visa", start_visa))  # New command
        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(CommandHandler("stopvisa", stop_visa))
        application.add_handler(CommandHandler("status", status))
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