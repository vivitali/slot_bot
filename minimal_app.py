import datetime
import logging
import os
import sys
import requests
import asyncio
import time
import threading
from flask import Flask, request
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

# Create Flask app for Cloud Run
app = Flask(__name__)

# Set up global application object
telegram_app = None

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
                await asyncio.sleep(1.5)  # Small delay between messages
                await bot.send_message(chat_id=chat_id, text="🪪🪪🪪🪪🪪🪪 ТЕРМІНОВО! ДОСТУПНИЙ ЗАПИС! 🪪🪪🪪🪪🪪🪪")
                await asyncio.sleep(1.5)  # Small delay between messages
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

# Define your other functions here (I'm keeping the previous functions)
# ...

# Flask routes for Cloud Run
@app.route('/', methods=['GET'])
def home():
    """Home route for health checks."""
    return "Visa Appointment Checker Bot is running! 🚀"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook route for Telegram updates."""
    if request.method == 'POST':
        # Get the update from Telegram
        update_data = request.get_json()
        # Log the update for debugging
        logger.info(f"Received update: {update_data}")
        return {'status': 'ok'}
    
    return {'status': 'error', 'message': 'Invalid request'}, 400

# Initialize the Telegram bot
def init_telegram_bot():
    """Initialize and start the Telegram bot."""
    global telegram_app
    
    # Get the bot token
    bot_token = os.getenv('TELEGRAM_TOKEN')
    
    if not bot_token:
        logger.error("Error: TELEGRAM_TOKEN not found in environment variables")
        return
    
    try:
        # Log that we're initializing the bot
        logger.info("Initializing Telegram bot...")
        # We'll implement this fully later, for now just return success
        logger.info("Bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize the bot: {str(e)}")
        return False

# Bot background thread function - simplified for testing
def bot_thread_function():
    """Function that runs in a background thread for the bot."""
    # Just log that the thread is running
    logger.info("Bot background thread is running...")
    # For testing, just keep the thread alive
    while True:
        time.sleep(60)
        logger.info("Bot thread still alive...")

if __name__ == '__main__':
    try:
        # Initialize the bot in a non-blocking way
        logger.info("Starting the application...")
        init_success = init_telegram_bot()
        logger.info(f"Bot initialization result: {init_success}")
        
        # Start a simple background thread
        logger.info("Starting bot background thread...")
        thread = threading.Thread(target=bot_thread_function)
        thread.daemon = True  # Allow the thread to exit when the main process exits
        thread.start()
        logger.info("Bot thread started")
        
        # Get the port from the environment variable
        port = int(os.getenv('PORT', 8080))
        logger.info(f"Starting Flask server on port {port}...")
        
        # Start the Flask app for Cloud Run - THIS IS THE CRITICAL PART
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Error starting the application: {e}")
        sys.exit(1)