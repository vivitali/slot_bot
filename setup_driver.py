# Selenium functions
import random

# Selenium related imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Import from our modules
from config_loader import load_config
from setup_logger import setup_logging

# Telegram related imports

# Initialize logger
logger = setup_logging()
# Load configuration
CONFIG = load_config()

def setup_driver():
    """Set up and return a configured Chrome WebDriver."""
    global driver
    
    try:
        logger.info("Setting up Chrome WebDriver...")
        
        chrome_options = Options()
        if CONFIG['HEADLESS']:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument('--profile-directory=Default')
        chrome_options.add_argument("--start-maximized")
        
        # Add random user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
        
        # Set up WebDriver based on configuration
        if CONFIG['LOCAL_USE']:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        else:
            driver = webdriver.Remote(command_executor=CONFIG['HUB_ADDRESS'], options=chrome_options)
        
        # Set implicit wait time
        driver.implicitly_wait(10)
        logger.info("WebDriver setup complete")
        
        return driver
    
    except Exception as e:
        logger.error(f"Failed to set up WebDriver: {e}")
        if CONFIG['DEBUG_MODE']:
            logger.debug(f"Detailed error: {str(e)}")
        return None
