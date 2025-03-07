import re
import time
import random
import logging
from typing import Dict, Tuple, Optional
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages the session with the visa appointment system, including login and session maintenance.
    """

    def __init__(self, username: str, password: str, country_code: str = "en-ca"):
        self.username = username
        self.password = password
        self.country_code = country_code
        self.session_cookie = None
        self.csrf_token = None
        self.session = requests.Session()

        # Set common headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept-Language': 'en-CA,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Connection': 'keep-alive'
        })

    def login_with_selenium(self, driver: webdriver.Chrome) -> bool:
        """
        Log in to the visa appointment system using Selenium.

        Args:
            driver: The Selenium WebDriver instance

        Returns:
            bool: True if login was successful, False otherwise
        """
        try:
            logger.info("Logging in with Selenium...")

            # Navigate to the main page
            driver.get(f"https://ais.usvisa-info.com/{self.country_code}/niv")
            time.sleep(random.uniform(1, 2))

            # Click continue if needed
            try:
                continue_link = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
                continue_link.click()
                time.sleep(random.uniform(0.5, 1))
            except:
                pass  # Continue link might not be present

            # Click on sign in
            try:
                sign_in_link = driver.find_element(By.XPATH,
                                                   '//*[@id="header"]/nav/div[1]/div[1]/div[2]/div[1]/ul/li[3]/a')
                sign_in_link.click()
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.error(f"Could not find sign in link: {e}")
                return False

            # Wait for the login form
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "user_email"))
                )
            except Exception as e:
                logger.error(f"Login form did not appear: {e}")
                return False

            # Enter credentials
            try:
                # Enter email
                email_field = driver.find_element(By.ID, "user_email")
                email_field.clear()
                for char in self.username:
                    email_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                time.sleep(random.uniform(0.5, 1))

                # Enter password
                password_field = driver.find_element(By.ID, "user_password")
                password_field.clear()
                for char in self.password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                time.sleep(random.uniform(0.5, 1))

                # Check the privacy checkbox
                checkbox = driver.find_element(By.CLASS_NAME, "icheckbox")
                checkbox.click()
                time.sleep(random.uniform(0.5, 1))

                # Click sign in
                sign_in_button = driver.find_element(By.NAME, "commit")
                sign_in_button.click()

                # Wait for successful login
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Sign Out')]"))
                )

                logger.info("Selenium login successful")

                # Extract session cookie
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie['name'] == '_yatri_session':
                        self.session_cookie = cookie['value']
                        logger.debug(f"Obtained session cookie: {self.session_cookie[:20]}...")

                # Extract CSRF token
                csrf_token_element = driver.find_element(By.XPATH, "//meta[@name='csrf-token']")
                if csrf_token_element:
                    self.csrf_token = csrf_token_element.get_attribute('content')
                    logger.debug(f"Obtained CSRF token: {self.csrf_token}")

                return True

            except Exception as e:
                logger.error(f"Error during Selenium login: {e}")
                return False

        except Exception as e:
            logger.error(f"Unexpected error in Selenium login: {e}")
            return False

    def is_session_valid(self) -> bool:
        """
        Check if the current session is valid.

        Returns:
            bool: True if the session is valid, False otherwise
        """
        if not self.session_cookie or not self.csrf_token:
            logger.warning("No session cookie or CSRF token available")
            return False

        try:
            # Try to access a protected resource
            url = f"https://ais.usvisa-info.com/{self.country_code}/niv/groups"

            headers = {
                'X-CSRF-Token': self.csrf_token,
                'X-Requested-With': 'XMLHttpRequest'
            }

            cookies = {
                '_yatri_session': self.session_cookie
            }

            response = requests.get(
                url,
                headers=headers,
                cookies=cookies,
                timeout=30
            )

            # If we get a successful response and not redirected to login
            return response.status_code == 200 and "Sign In" not in response.text

        except Exception as e:
            logger.error(f"Error checking session validity: {e}")
            return False

    def get_session_details(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the current session cookie and CSRF token.

        Returns:
            Tuple containing the session cookie and CSRF token
        """
        return self.session_cookie, self.csrf_token