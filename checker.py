#!/usr/bin/env python3
"""
US Visa Appointment Checker

This script checks for available US visa appointments and loads all configuration from a .env file.

Features:
1. Check for available appointments at a specific facility
2. Check available dates and times
3. Send notifications when slots become available

Configuration is read from a .env file in the same directory.

Usage:
    python visa_checker.py [--continuous] [--interval 300]

Optional Arguments:
    --continuous: Run in continuous mode, checking periodically
    --interval: Check interval in seconds for continuous mode (default: 300)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

class VisaAppointmentChecker:
    def __init__(self, email, password, schedule_id, country_code="en-ca", visa_type="niv", facility_id=None):
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
            print("Failed to extract CSRF token")
            return None
            
        return csrf_token_meta['content']
    
    def login(self):
        """Log in to the visa appointment system"""
        try:
            # Initial request to get CSRF token
            print("Fetching login page to get CSRF token...")
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
                print("Failed to obtain CSRF token")
                return False
            
            print(f"CSRF token obtained: {self.csrf_token[:10]}...")
            
            # Perform login
            print(f"Logging in with email: {self.email}...")
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
                print("Login successful")
                self.is_logged_in = True
                return True
            else:
                print("Login failed - incorrect credentials or captcha required")
                return False
                
        except requests.RequestException as e:
            print(f"Error during login: {e}")
            return False
    
    def check_appointment_availability(self):
        """Check if appointments are available in the payment page"""
        if not self.is_logged_in and not self.login():
            print("Not logged in. Please log in first.")
            return False
        
        try:
            print("Checking appointment availability...")
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
                print("No available appointments.")
                return False
            else:
                print("Appointments available!")
                return True
                
        except requests.RequestException as e:
            print(f"Error checking appointment availability: {e}")
            return False
    
    def get_available_dates(self):
        """Get available appointment dates for a specific facility"""
        if not self.facility_id:
            print("No facility ID specified. Cannot check available dates.")
            return []
            
        if not self.is_logged_in and not self.login():
            print("Not logged in. Please log in first.")
            return []
        
        try:
            print(f"Checking available dates for facility {self.facility_id}...")
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
                    print(f"Found {len(dates)} available dates:")
                    for date in dates[:5]:  # Show first 5 dates
                        print(f"  {date.get('date')} - Business day: {date.get('business_day')}")
                    
                    if len(dates) > 5:
                        print(f"  ... and {len(dates) - 5} more dates")
                else:
                    print("No available dates found")
                
                return dates
            except json.JSONDecodeError:
                print("Failed to parse dates response as JSON")
                print(f"Response: {response.text[:200]}...")
                return []
                
        except requests.RequestException as e:
            print(f"Error fetching available dates: {e}")
            return []
    
    def get_available_times(self, date):
        """Get available appointment times for a specific date"""
        if not self.facility_id:
            print("No facility ID specified. Cannot check available times.")
            return []
            
        if not self.is_logged_in and not self.login():
            print("Not logged in. Please log in first.")
            return []
        
        try:
            print(f"Checking available times for date {date}...")
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
                    print(f"Found {len(available_times)} available times:")
                    for time_slot in available_times:
                        print(f"  {time_slot}")
                else:
                    print("No available times found for this date")
                
                return available_times
            except json.JSONDecodeError:
                print("Failed to parse times response as JSON")
                print(f"Response: {response.text[:200]}...")
                return []
                
        except requests.RequestException as e:
            print(f"Error fetching available times: {e}")
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
            print("Login failed. Cannot check appointments.")
            return False
        
        # Check general availability
        has_appointments = self.check_appointment_availability()
        
        # If facility ID is provided, check specific dates and times
        if has_appointments and self.facility_id:
            print("\nFetching available dates:")
            dates = self.get_available_dates()
            
            if dates:
                # Get times for the first available date
                first_date = dates[0].get('date')
                print(f"\nFetching available times for the first date ({first_date}):")
                times = self.get_available_times(first_date)
        
        return has_appointments

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
        'check_interval': int(os.getenv('CHECK_INTERVAL', '300')),
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
        config['check_interval'] = args.interval
    
    # Create checker instance
    checker = VisaAppointmentChecker(
        config['email'],
        config['password'],
        config['schedule_id'],
        config['country_code'],
        config['visa_type'],
        config['facility_id']
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