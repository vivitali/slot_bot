import json
import requests
import logging
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def get_available_dates(
        session_cookie: str,
        csrf_token: str,
        schedule_id: str,
        facility_id: str,
        country_code: str = "en-ca",
        is_expedite: bool = False
) -> List[Dict]:
    """
    Get available appointment dates using direct HTTP request instead of Selenium.

    Args:
        session_cookie: The _yatri_session cookie value
        csrf_token: The X-CSRF-Token value
        schedule_id: The schedule ID (e.g., "66488302")
        facility_id: The facility ID (e.g., "94")
        country_code: The country code (default: "en-ca")
        is_expedite: Whether this is an expedited appointment (default: False)

    Returns:
        List of available dates as dictionaries
    """
    # Construct the URL
    url = f"https://ais.usvisa-info.com/{country_code}/niv/schedule/{schedule_id}/appointment/days/{facility_id}.json?appointments[expedite]=false"

    # Prepare headers
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-CA,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': f'https://ais.usvisa-info.com/{country_code}/niv/schedule/{schedule_id}/appointment',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'X-CSRF-Token': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
        'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"'
    }

    # Prepare cookies
    cookies = {
        '_yatri_session': session_cookie
    }

    logger.info(f"Fetching available dates from {url}")

    try:
        # Make the request
        response = requests.get(
            url,
            headers=headers,
            cookies=cookies,
            timeout=30
        )

        # Raise an exception for bad status codes
        # response.raise_for_status()

        # Parse JSON response
        data = response.json()

        logger.info(f"Successfully fetched {len(data)} date entries")
        return data

    except requests.RequestException as e:
        logger.error(f"Error fetching appointment dates: {e}")
        # If there's a response, log it for debugging
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text[:500]}...")  # Log first 500 chars
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {e}")
        logger.error(f"Response text: {response.text[:500]}...")  # Log first 500 chars
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []


def get_available_times(
        session_cookie: str,
        csrf_token: str,
        schedule_id: str,
        facility_id: str,
        date: str,
        country_code: str = "en-ca",
        is_expedite: bool = False
) -> List[str]:
    """
    Get available appointment times for a specific date using direct HTTP request.

    Args:
        session_cookie: The _yatri_session cookie value
        csrf_token: The X-CSRF-Token value
        schedule_id: The schedule ID (e.g., "66488302")
        facility_id: The facility ID (e.g., "94")
        date: The date to check in YYYY-MM-DD format
        country_code: The country code (default: "en-ca")
        is_expedite: Whether this is an expedited appointment (default: False)

    Returns:
        List of available times as strings
    """
    # Construct the URL
    url = f"https://ais.usvisa-info.com/{country_code}/niv/schedule/{schedule_id}/appointment/times/{facility_id}.json"

    # Add query parameters
    params = {
        "date": date,
        "appointments[expedite]": "true" if is_expedite else "false"
    }

    # Prepare headers
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-CA,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': f'https://ais.usvisa-info.com/{country_code}/niv/schedule/{schedule_id}/appointment',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'X-CSRF-Token': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
        'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"'
    }

    # Prepare cookies
    cookies = {
        '_yatri_session': session_cookie
    }

    logger.info(f"Fetching available times for date {date}")

    try:
        # Make the request
        response = requests.get(
            url,
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=30
        )

        # Raise an exception for bad status codes
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Extract available times
        available_times = data.get('available_times', [])

        logger.info(f"Successfully fetched {len(available_times)} time slots for date {date}")
        return available_times

    except requests.RequestException as e:
        logger.error(f"Error fetching appointment times: {e}")
        # If there's a response, log it for debugging
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text[:500]}...")  # Log first 500 chars
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {e}")
        logger.error(f"Response text: {response.text[:500]}...")  # Log first 500 chars
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []