import logging
import os
import sys
import requests
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters

# Load environment variables
load_dotenv()

# Set up logging with more details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more detailed logs
)

# Dictionary to track active loop tasks
active_loops = {}

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
        logging.error(f"Error in loop messages: {str(e)}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"An error occurred in the loop: {str(e)}"
        )

# Define the start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command with or without loop parameter."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if arguments were provided
    if context.args and context.args[0].lower() == 'loop':
        # Cancel any existing loop for this user
        if user_id in active_loops:
            # Get the task
            task = active_loops[user_id]
            
            # Cancel the task
            task.cancel()
            
            # Try to wait for the task to be cancelled
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            
            await update.message.reply_text('Stopping previous loop and starting a new one...')
        
        # Start a background task for this user
        task = asyncio.create_task(send_loop_messages(context.bot, chat_id, user_id))
        
        # Store the task in the active_loops dictionary
        active_loops[user_id] = task
        
        await update.message.reply_text('Starting loop messages every 3 seconds. Send /stop to stop the loop.')
    else:
        # Regular start command
        await update.message.reply_text('Hello! I am your Telegram bot. Thanks for starting me!\n\nUse "/start loop" to receive messages every 3 seconds.')

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

def check_token_validity(token):
    """Verify if the token is valid by making a request to Telegram API"""
    try:
        response = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            print(f"Token is valid! Bot name: {bot_info['result']['first_name']}")
            return True
        else:
            print(f"Token seems invalid. Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error checking token: {str(e)}")
        return False

def check_internet_connection():
    """Check if there's a working internet connection"""
    try:
        # Try to reach Telegram's API
        response = requests.get('https://api.telegram.org', timeout=5)
        print("Internet connection: OK")
        return True
    except requests.ConnectionError:
        print("Internet connection: FAILED - Cannot reach Telegram API")
        return False
    except Exception as e:
        print(f"Internet connection check error: {str(e)}")
        return False

def main():
    # Get the bot token from environment variables
    bot_token = os.getenv('TELEGRAM_TOKEN')
    
    if not bot_token:
        print("Error: TELEGRAM_TOKEN not found in .env file")
        sys.exit(1)
    
    # Check internet connection
    if not check_internet_connection():
        print("Please check your internet connection and try again.")
        sys.exit(1)
    
    # Verify token validity
    if not check_token_validity(bot_token):
        print("Please verify your bot token and try again.")
        sys.exit(1)
    
    try:
        # Create the application with proxy settings if needed
        application_builder = ApplicationBuilder().token(bot_token)
        
        # Uncomment and modify the following line if you need to use a proxy
        # application_builder.proxy_url('socks5://proxy_address:proxy_port')
        
        application = application_builder.build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stop", stop))
        
        # Start the Bot
        print("Bot is starting...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Failed to start the bot: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == '__main__':
    main()