import json
import logging
import os
import re
import requests
from bs4 import BeautifulSoup

from constants import DEFAULT_CHECK_INTERVAL

from utils import get_random_interval

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VisaAppointmentChecker:
    def __init__(self, email, password, schedule_id, country_code="en-ca", visa_type="niv", facility_id=None, check_interval=300):
        """
        Initialize the visa appointment checker.
        
        Args:
            email: Your login email
            password: Your login password
            schedule_id: The schedule ID from the URL
            country_code: Country code (default: "en-ca" for Canada)
            visa_type: Visa type (default: "niv" for non-immigrant visa)
            facility_id: Facility ID to check (default: None, checks all)
        """
        self.email = email
        self.password = password
        self.schedule_id = schedule_id
        self.country_code = country_code
        self.visa_type = visa_type
        self.facility_id = facility_id
        self.check_interval = check_interval
        # Session and auth data
        self.session = requests.Session()
        self.csrf_token = None
        self.is_logged_in = False
        
        # Define URLs
        self.base_url = f"https://ais.usvisa-info.com/{country_code}/{visa_type}"
        self.login_url = f"{self.base_url}/users/sign_in"
        self.appointment_url = f"{self.base_url}/schedule/{schedule_id}/appointment"
        self.payment_url = f"{self.base_url}/schedule/{schedule_id}/payment"
        
        # Build date and time URLs if facility_id is provided
        if facility_id:
            self.date_url = f"{self.base_url}/schedule/{schedule_id}/appointment/days/{facility_id}.json?appointments[expedite]=false"
            self.time_url = f"{self.base_url}/schedule/{schedule_id}/appointment/times/{facility_id}.json?date=%s&appointments[expedite]=false"
        
        # Common headers
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        self.common_headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "DNT": "1",
            "sec-ch-ua": '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
    
    def get_csrf_token(self, response_text):
        """Extract CSRF token from HTML response"""
        soup = BeautifulSoup(response_text, 'html.parser')
        csrf_token_meta = soup.find('meta', {'name': 'csrf-token'})
        
        if not csrf_token_meta:
            logger.error("Failed to extract CSRF token")
            return None
            
        return csrf_token_meta['content']
    
    def login(self):
        """Log in to the visa appointment system"""
        try:
            # Initial request to get CSRF token
            logger.info("Fetching login page to get CSRF token...")
            headers = {
                **self.common_headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
            
            response = self.session.get(self.login_url, headers=headers)
            response.raise_for_status()
            
            # Extract CSRF token
            self.csrf_token = self.get_csrf_token(response.text)
            if not self.csrf_token:
                logger.error("Failed to obtain CSRF token")
                return False
            
            logger.info(f"CSRF token obtained: {self.csrf_token[:10]}...")
            
            # Perform login
            logger.info(f"Logging in with email: {self.email}...")
            login_headers = {
                **self.common_headers,
                "Accept": "*/*;q=0.5, text/javascript, application/javascript, application/ecmascript, application/x-ecmascript",
                "Origin": "https://ais.usvisa-info.com",
                "Referer": self.login_url,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            
            login_data = {
                "user[email]": self.email,
                "user[password]": self.password,
                "policy_confirmed": "1",
                "commit": "Sign In"
            }
            
            login_response = self.session.post(
                self.login_url,
                headers=login_headers,
                data=login_data
            )
            
            login_response.raise_for_status()
            
            # Check if login was successful - redirected to account page
            if login_response.status_code == 200:
                logger.info("Login successful")
                self.is_logged_in = True
                return True
            else:
                logger.error("Login failed - incorrect credentials or captcha required")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Error during login: {e}")
            return False
    
    def check_appointment_availability(self):
        """Check if appointments are available in the payment page"""
        if not self.is_logged_in and not self.login():
            logger.error("Not logged in. Please log in first.")
            return False
        
        try:
            logger.info("Checking appointment availability...")
            headers = {
                **self.common_headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Referer": self.login_url,
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
            
            response = self.session.get(self.payment_url, headers=headers)
            response.raise_for_status()
            
            if "There are no available appointments" in response.text:
                logger.info("No available appointments.")
                return False
            else:
                logger.info("Appointments available!")
                return True
                
        except requests.RequestException as e:
            logger.error(f"Error checking appointment availability: {e}")
            return False
    
    def get_available_dates(self):
        """Get available appointment dates for a specific facility"""
        if not self.facility_id:
            logger.error("No facility ID specified. Cannot check available dates.")
            return []
            
        if not self.is_logged_in and not self.login():
            logger.error("Not logged in. Please log in first.")
            return []
        
        try:
            logger.info(f"Checking available dates for facility {self.facility_id}...")
            headers = {
                **self.common_headers,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": self.appointment_url,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest"
            }
            
            response = self.session.get(self.date_url, headers=headers)
            response.raise_for_status()
            
            try:
                dates = response.json()
                if dates:
                    logger.info(f"Found {len(dates)} available dates")
                    for date in dates[:5]:  # Show first 5 dates
                        logger.info(f"  {date.get('date')} - Business day: {date.get('business_day')}")
                    
                    if len(dates) > 5:
                        logger.info(f"  ... and {len(dates) - 5} more dates")
                else:
                    logger.info("No available dates found")
                
                return dates
            except json.JSONDecodeError:
                logger.error("Failed to parse dates response as JSON")
                logger.error(f"Response: {response.text[:200]}...")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Error fetching available dates: {e}")
            return []
    
    def get_available_times(self, date):
        """Get available appointment times for a specific date"""
        if not self.facility_id:
            logger.error("No facility ID specified. Cannot check available times.")
            return []
            
        if not self.is_logged_in and not self.login():
            logger.error("Not logged in. Please log in first.")
            return []
        
        try:
            logger.info(f"Checking available times for date {date}...")
            time_url = self.time_url % date
            
            headers = {
                **self.common_headers,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": self.appointment_url,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest"
            }
            
            response = self.session.get(time_url, headers=headers)
            response.raise_for_status()
            
            try:
                data = response.json()
                available_times = data.get('available_times', [])
                
                if available_times:
                    logger.info(f"Found {len(available_times)} available times")
                    for time_slot in available_times:
                        logger.info(f"  {time_slot}")
                else:
                    logger.info("No available times found for this date")
                
                return available_times
            except json.JSONDecodeError:
                logger.error("Failed to parse times response as JSON")
                logger.error(f"Response: {response.text[:200]}...")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Error fetching available times: {e}")
            return []
    
    def get_session_details(self):
        """Return the current session cookie and CSRF token for reuse"""
        cookies = {cookie.name: cookie.value for cookie in self.session.cookies}
        
        # Find the yatri session cookie
        session_cookie = cookies.get('_yatri_session')
        
        return {
            'session_cookie': session_cookie,
            'csrf_token': self.csrf_token,
            'cookies': cookies,
            'headers': self.session.headers
        }
    
    def check_and_print_availability(self):
        """Full check of appointment availability with detailed output"""
        if not self.login():
            logger.error("Login failed. Cannot check appointments.")
            return False
        
        # Check general availability
        
        # If facility ID is provided, check specific dates and times
        if self.facility_id:
            logger.info("\nFetching available dates:")
            dates = self.get_available_dates()
            
            if dates:
                # Get times for the first available date
                first_date = dates[0].get('date')
                logger.info(f"\nFetching available times for the first date ({first_date}):")
                times = self.get_available_times(first_date)
        
        return True

# If this file is run directly, it can still function as a standalone script
if __name__ == "__main__":
    import sys
    import time
    import argparse
    from dotenv import load_dotenv
    from datetime import datetime
    
    def load_config():
        """Load configuration from .env file"""
        # Load .env file
        load_dotenv()
        
        # Required parameters
        required_params = ['VISA_EMAIL', 'VISA_PASSWORD', 'SCHEDULE_ID']
        missing_params = [param for param in required_params if not os.getenv(param)]
        
        if missing_params:
            print(f"Error: Missing required parameters in .env file: {', '.join(missing_params)}")
            print("Please create a .env file with the required parameters.")
            sys.exit(1)
        
        # Load parameters
        config = {
            'email': os.getenv('VISA_EMAIL'),
            'password': os.getenv('VISA_PASSWORD'),
            'schedule_id': os.getenv('SCHEDULE_ID'),
            'country_code': os.getenv('COUNTRY_CODE', 'en-ca'),
            'visa_type': os.getenv('VISA_TYPE', 'niv'),
            'facility_id': os.getenv('FACILITY_ID'),
            'check_interval': get_random_interval(int(os.getenv('CHECK_INTERVAL', DEFAULT_CHECK_INTERVAL))),
        }
        
        print(f"Configuration loaded successfully:")
        print(f"  Email: {config['email']}")
        print(f"  Schedule ID: {config['schedule_id']}")
        print(f"  Country Code: {config['country_code']}")
        print(f"  Visa Type: {config['visa_type']}")
        print(f"  Facility ID: {config['facility_id'] or 'Not specified'}")
        print(f"  Check Interval: {config['check_interval']} seconds")
        
        return config
    
    def main():
        parser = argparse.ArgumentParser(description="Check for available US visa appointments")
        parser.add_argument("--continuous", action="store_true", help="Run in continuous mode, checking periodically")
        parser.add_argument("--interval", type=int, help="Check interval in seconds for continuous mode (overrides .env)")
        
        args = parser.parse_args()
        
        # Load configuration from .env file
        config = load_config()
        
        # Override interval from command line if provided
        if args.interval:
            print(f"Overriding check interval to {args.interval} seconds")
            config['check_interval'] = args.interval
        
        # Create checker instance
        checker = VisaAppointmentChecker(
            config['email'],
            config['password'],
            config['schedule_id'],
            config['country_code'],
            config['visa_type'],
            config['facility_id'],
            config['check_interval']
        )
        
        if args.continuous:
            print(f"Running in continuous mode, checking every {config['check_interval']} seconds. Press Ctrl+C to stop.")
            try:
                while True:
                    print(f"\n=== Check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
                    checker.check_and_print_availability()
                    print(f"Sleeping for {config['check_interval']} seconds...")
                    time.sleep(config['check_interval'])
            except KeyboardInterrupt:
                print("\nExiting continuous mode.")
        else:
            checker.check_and_print_availability()

    if __name__ == "__main__":
        main()