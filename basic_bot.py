import logging
import os
import sys
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
load_dotenv()

# Set up logging with more details
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Changed to DEBUG for more detailed logs
)


# Define the start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    await update.message.reply_text('Hello! I am your Telegram bot. Thanks for starting me!')


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
    bot_token = os.getenv('TELEGCannot reach Telegram APIRAM_TOKEN')

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

        # Start the Bot
        print("Bot is starting...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Failed to start the bot: {str(e)}")
        import traceback
        print(traceback.format_exc())


if __name__ == '__main__':
    main()