import * as cheerio from 'cheerio';
import fetch from 'node-fetch';
import sgMail from '@sendgrid/mail';
import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// Use environment variables instead of hard-coded values
const USERNAME = process.env.VISA_USERNAME;
const PASSWORD = process.env.VISA_PASSWORD;
const SCHEDULE_ID = process.env.SCHEDULE_ID;
const MY_SCHEDULE_DATE = process.env.MY_SCHEDULE_DATE;
const BASE_URL = 'https://ais.usvisa-info.com/' + process.env.COUNTRY_CODE + '/niv';
const NOTIFICATION_EMAIL = process.env.NOTIFICATION_EMAIL || process.env.VISA_USERNAME;
const CHECK_INTERVAL = parseInt(process.env.CHECK_INTERVAL) || 5; // Minutes

// Set SendGrid API key from environment variable
sgMail.setApiKey(process.env.SEND_GRID_API_KEY);

const listOfEmbassies = [
  { id: 89, name: "Calgary" },
  { id: 90, name: "Halifax" },
  { id: 91, name: "Montreal" },
  { id: 92, name: "Ottawa" },
  { id: 93, name: "Quebec City" },
  { id: 94, name: "Toronto" },
  { id: 95, name: "Vancouver" },
];

let bestAvailableEmbassy = null;
let bestAvailableDate = null;
let bestAvailableTime = null;

// At the beginning, prioritize the facility from the .env file
const preferredFacilityId = parseInt(process.env.FACILITY_ID);

// When checking embassies, check the preferred one first
const embassyToCheck = listOfEmbassies.find(e => e.id === preferredFacilityId) || listOfEmbassies[0];
console.log(`Checking preferred embassy: ${embassyToCheck.name}`);

async function main(currentAppointmentDate) {

  if (!currentAppointmentDate) {
    console.log(`Invalid current appointment date: ${currentAppointmentDate}`)
    process.exit(1)
  }

  console.log(`Current appointment date: ${currentAppointmentDate}`)

  const message = {
    to: NOTIFICATION_EMAIL,
    from: NOTIFICATION_EMAIL,
    subject: 'USA VISA Appointment available date started!',
    text: 'USA VISA Appointment available date started!',
  }

  sgMail.send(message)
    .then((response) => {
      console.log(response[0].statusCode)
      console.log(response[0].headers)
    })
    .catch(error => console.log(`Error sending email: ${error.message}`));

  try {

    while (!bestAvailableDate) {

      const sessionHeaders = await authentication()

      console.log('Authentication process - OK')


        const date = await findAvailableDate(sessionHeaders, embassyToCheck.id);
  
        if (!date) {
          console.log(`Embassy: ${embassyToCheck.name}. Status: No available dates found!`);
        } else if (date > currentAppointmentDate) {
          console.log(`Embassy: ${embassyToCheck.name}. Status: Nearest date ${date} is further than already booked!`);
        } else {
  
          const time = await findAvailableTime(sessionHeaders, date, embassyToCheck.id);
  
          console.log(`Embassy - ${embassyToCheck.name}. Status: Closest date and time: ${date} (${time})`);
          
          if (!bestAvailableDate || (date < bestAvailableDate)) {
            bestAvailableEmbassy = embassyToCheck.name;
            bestAvailableDate = date;
            bestAvailableTime = time;
          }
        }

      console.log('Wait for ' + CHECK_INTERVAL + ' minutes!')
      await sleep(60 * CHECK_INTERVAL);
    }

    if (bestAvailableDate) {

      const emailContent = `Best available date across all embassies found! Embassy: ${bestAvailableEmbassy}, date and time: ${bestAvailableDate} (${bestAvailableTime})`;
      console.log(emailContent);

      const message = {
        to: NOTIFICATION_EMAIL,
        from: NOTIFICATION_EMAIL,
        subject: 'USA VISA Appointment available date found!',
        text: emailContent,
      }

      sgMail.send(message)
        .then((response) => {
          console.log(response[0].statusCode)
          console.log(response[0].headers)
        })
        .catch(error => log(`Error sending email: ${error.message}`));

      console.log(bestAvailableDate, bestAvailableTime)

      // GET Embassy information - name, facility ID
      const embassy = listOfEmbassies.find((embassy) => embassy.name === bestAvailableEmbassy);

      // GET Facility ID
      const facilityId = embassy.id;

      // Book New Appointment
      console.log('Attempt to book new appointment!')
      bookAppointment(sessionHeaders, bestAvailableDate, bestAvailableTime, facilityId)
        .then(d => console.log(`New appointment booked! Date and time: ${bestAvailableDate} (${bestAvailableTime}). Embassy: ${bestAvailableEmbassy}.`))

    } else {
      console.log('Unfortunately, no available dates found!');
    }

    console.log('Process - DONE!')

  } catch (error) {
    console.error(error)
    main(currentAppointmentDate)
  }
}

async function authentication() {

  console.log(`Authentication process started`);

  const anonymousHeaders = await fetch(`${BASE_URL}/users/sign_in`)
    .then(response => extractHeaders(response));

  const response = await fetch(`${BASE_URL}/users/sign_in`, {
    method: "POST",
    headers: {
      ...anonymousHeaders,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: new URLSearchParams({
      'utf8': '✓',
      'user[email]': USERNAME,
      'user[password]': PASSWORD,
      'policy_confirmed': '1',
      'commit': 'Sign In'
    }),
  });

  if (!response.ok) {
    throw new Error('Authentication process failed');
  }

  const authenticatedHeaders = {
    ...anonymousHeaders,
    'Cookie': extractRelevantCookies(response),
  };

  return authenticatedHeaders;
}

async function extractHeaders(response) {

  try {
    const cookies = extractRelevantCookies(response);
    const html = await response.text();
    const tokenCSRF = extractCSRFToken(html);

    return {
      "Cookie": cookies,
      "X-CSRF-Token": tokenCSRF,
      "Referer": BASE_URL,
      "Referrer-Policy": "strict-origin-when-cross-origin",
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
      'Cache-Control': 'no-store',
      'Connection': 'keep-alive'
    };
  } catch (error) {
    console.error("Error extracting headers: ", error.message);
    throw error;
  }
}

function extractCSRFToken(html) {

  const $ = cheerio.load(html);
  const tokenCSFT = $('meta[name="csrf-token"]').attr('content');

  if (!tokenCSFT) {
    throw new Error("CSRF token not found in HTML");
  }

  return tokenCSFT;
}

function extractRelevantCookies(res) {
  const parsedCookies = parseCookies(res.headers.get('set-cookie'));
  return `_yatri_session=${parsedCookies['_yatri_session']}`;
}

function parseCookies(cookies) {
  return cookies
    ? cookies
      .split(';')
      .map((c) => c.trim().split('=')) // Split each cookie into [name, value]
      .reduce((acc, [name, value]) => {
        acc[name] = value;
        return acc;
      }, {})
    : {};
}

function findAvailableDate(headers, embassyId) {

  return fetch(`${BASE_URL}/schedule/${SCHEDULE_ID}/appointment/days/${embassyId}.json?appointments[expedite]=false`, {
    "headers": Object.assign({}, headers, {
      "Accept": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    }),
    "cache": "no-store"
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`Fetch data - fail. Status: ${response.status}`);
      }
      return response.json();
    })
    .then(r => handleError(r))
    .then(d => d.length > 0 ? d[0]['date'] : null)
    .catch(error => {
      console.log(`Fetch data - error with message: ${error.message}`);
      return null;
    });
}

function findAvailableTime(headers, date, embassyId) {
  return fetch(`${BASE_URL}/schedule/${SCHEDULE_ID}/appointment/times/${embassyId}.json?date=${date}&appointments[expedite]=false`, {
    "headers": Object.assign({}, headers, {
      "Accept": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    }),
    "cache": "no-store"
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`Fetch data - fail. Status: ${response.status}`);
      }
      return response.json();
    })
    .then(r => handleError(r))
    .then(d => d['business_times'][0] || d['available_times'][0])
    .catch(error => {
      console.log(`Fetch data - error with message: ${error.message}`);
      return null;
    });
}

async function bookAppointment(sessionHeaders, date, time, facilityId) {

  const url = `${BASE_URL}/schedule/${SCHEDULE_ID}/appointment`;

  const headers = await fetch(url, {sessionHeaders}).then(response => extractHeaders(response));

  const requestBody = new URLSearchParams({
    'utf8': '✓',
    'authenticity_token': headers['X-CSRF-Token'],
    'confirmed_limit_message': '1',
    'use_consulate_appointment_capacity': 'true',
    'appointments[consulate_appointment][facility_id]': facilityId,
    'appointments[consulate_appointment][date]': date,
    'appointments[consulate_appointment][time]': time,
    'appointments[asc_appointment][facility_id]': '',
    'appointments[asc_appointment][date]': '',
    'appointments[asc_appointment][time]': ''
  });

  const response = await fetch(url, {
    method: 'POST',
    redirect: 'follow',
    headers: {
      ...headers,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: requestBody,
  });

  return response;
}

function handleError(response) {

  const { error } = response;

  if (error) {
    throw new Error(error);
  }

  return response;
}

function sleep(seconds) {
  return new Promise(resolve => setTimeout(resolve, seconds * 1000));
}

const args = process.argv.slice(2);
const currentAppointmentDate = args[0] || MY_SCHEDULE_DATE;
main(currentAppointmentDate)