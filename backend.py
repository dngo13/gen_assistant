from flask import Flask, jsonify, request, render_template_string
from googleapiclient.discovery import build
import datetime
import time
from calendar_auth import get_calendar_service
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import pytz
from bot_run import send_reminder_to_discord # Import the send function from the bot file
import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import os
app = Flask(__name__)

# Fetch upcoming events from Google Calendar
@app.route('/get_upcoming_events')
def get_upcoming_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    # Create a list of simplified event details
    event_list = []
    current_time = time.time()
    with app.app_context():
        try:
            service = build('calendar', 'v3', credentials=creds)
            # Get all available calendars
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            # Get events starting from now to the next day
            # now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            now = datetime.datetime.now(pytz.timezone('America/New_York')).isoformat()  # Current time in America/New_York ## WORKING
            # now = datetime.datetime.now(datetime.datetime.eastern).isoformat()
            all_events = []
            print("Getting the upcoming 5 events")
            for calendar in calendars:
                # Fetch the calendar time zone
                calendar_timezone = calendar.get('timeZone', 'UTC')  # Default to UTC if no time zone is set
                calendar_id = calendar['id']
                is_work_calendar = 'h2t10ssk3fh0pmihaui72a4mlsh10i1g@import.calendar.google.com' in calendar_id
                events_result = (
                    service.events()
                    .list(
                        calendarId=calendar_id, 
                        timeMin=now,
                        maxResults=5, 
                        singleEvents=True, 
                        orderBy='startTime',
                        timeZone=calendar_timezone  # Specify the time zone
                    )
                    .execute()
                )
                events = events_result.get('items', [])
                print(f"Calendar: {calendar_id}, Time Zone: {calendar_timezone}")                
                if not events:
                    print(f"No upcoming events for calendar: {calendar_id}")
                    continue
                all_events.extend(events)
                
                for event in events:
                    print("Printing events")
                    summary = event.get('summary', 'No Title')  # Get the event summary or provide a fallback
                    start_time = event['start'].get('dateTime', event['start'].get('date'))
                    # Log start_time to ensure the format is correct
                    print(f"Raw start_time from event: {start_time}. {summary}")

                    if is_work_calendar:
                        utc_start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        start_time = utc_start_time.astimezone(pytz.timezone('America/New_York'))
                        print(f"Converted start_time for work calendar: {start_time}, {summary}")
                    else:
                        # Handle other calendars (ensure they're in the correct timezone)
                        start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00')).astimezone(pytz.timezone(calendar_timezone))
                    description = event.get('description', 'No description provided')  # Get the event description or provide a fallback
                    if len(description) > 100:
                        description = "Project Meeting with Team"
                    event_list.append({
                        'summary': summary,
                        'start_time': start_time.isoformat(),
                        'description' : description
                    })
                # Sort events by start time and take the top 5
                event_list.sort(key=lambda x: x['start_time'])  # Sort by start_time
                event_list = event_list[:5]  # Limit to 5 events
                for event in event_list:
                    schedule_event_notifications(event['summary'], event['start_time'], event['description'])
                print(event_list)
        except Exception as e:
            print(f"An error occurred in getting upcoming events: {e}")
    return jsonify({'events': event_list})

# Summarize events to send to Home assistant
# Function to get daily events for all calendars and send
def get_daily_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    # Create a list of simplified event details
    event_list = []
    current_time = time.time()
    with app.app_context():
        try:
            service = build('calendar', 'v3', credentials=creds)
            # Get all available calendars
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            # Get events starting from now to the next day
            # now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            now = datetime.datetime.now(pytz.timezone('America/New_York')).isoformat()  # Current time in America/New_York ## WORKING
            # now = datetime.datetime.now(datetime.datetime.eastern).isoformat()
            end_of_day = (datetime.datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)).isoformat() + 'Z'
            all_events = []
            print("Getting the upcoming 5 events")
            for calendar in calendars:
                # Fetch the calendar time zone
                calendar_timezone = calendar.get('timeZone', 'UTC')  # Default to UTC if no time zone is set
                calendar_id = calendar['id']
                is_work_calendar = 'h2t10ssk3fh0pmihaui72a4mlsh10i1g@import.calendar.google.com' in calendar_id
                events_result = (
                    service.events()
                    .list(
                        calendarId=calendar_id, 
                        timeMin=now,
                        timeMax=end_of_day,
                        maxResults=5, 
                        singleEvents=True, 
                        orderBy='startTime',
                        timeZone=calendar_timezone  # Specify the time zone
                    )
                    .execute()
                )
                events = events_result.get('items', [])
                print(f"Calendar: {calendar_id}, Time Zone: {calendar_timezone}")                
                if not events:
                    print(f"No upcoming events for calendar: {calendar_id}")
                    continue
                all_events.extend(events)
                
                for event in events:
                    print("Printing events")
                    summary = event.get('summary', 'No Title')  # Get the event summary or provide a fallback
                    start_time = event['start'].get('dateTime', event['start'].get('date'))
                    # Log start_time to ensure the format is correct
                    print(f"Raw start_time from event: {start_time}. {summary}")
                    # formatted_start_time = format_date(start_time)  # Format the date in 12-hour format
                
                    if is_work_calendar:
                        utc_start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        start_time = utc_start_time.astimezone(pytz.timezone('America/New_York'))
                        print(f"Converted start_time for work calendar: {start_time}, {summary}")
                    else:
                        # Handle other calendars (ensure they're in the correct timezone)
                        start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00')).astimezone(pytz.timezone(calendar_timezone))
                    description = event.get('description', 'No description provided')  # Get the event description or provide a fallback
                    if len(description) > 150:
                        description = "Project Meeting with Team"
                    event_list.append({
                        'summary': summary,
                        'start_time': start_time.isoformat(),
                        'description' : description
                    })
                # Sort events by start time and take the top 5
                event_list.sort(key=lambda x: x['start_time'])  # Sort by start_time
                event_list = event_list[:5]  # Limit to 5 events
        except Exception as e:
            print(f"An error occurred in sending today's events: {e}")
    return event_list

# Function to get daily events for all calendars and send
def send_daily_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    # Create a list of simplified event details
    event_list = []
    current_time = time.time()
    with app.app_context():
        try:
            service = build('calendar', 'v3', credentials=creds)
            # Get all available calendars
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            # Get events starting from now to the next day
            # now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            now = datetime.datetime.now(pytz.timezone('America/New_York')).isoformat()  # Current time in America/New_York ## WORKING
            # now = datetime.datetime.now(datetime.datetime.eastern).isoformat()
            end_of_day = (datetime.datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)).isoformat() + 'Z'
            all_events = []
            print("Getting the upcoming 5 events")
            for calendar in calendars:
                # Fetch the calendar time zone
                calendar_timezone = calendar.get('timeZone', 'UTC')  # Default to UTC if no time zone is set
                calendar_id = calendar['id']
                is_work_calendar = 'h2t10ssk3fh0pmihaui72a4mlsh10i1g@import.calendar.google.com' in calendar_id
                events_result = (
                    service.events()
                    .list(
                        calendarId=calendar_id, 
                        timeMin=now,
                        timeMax=end_of_day,
                        maxResults=5, 
                        singleEvents=True, 
                        orderBy='startTime',
                        timeZone=calendar_timezone  # Specify the time zone
                    )
                    .execute()
                )
                events = events_result.get('items', [])
                print(f"Calendar: {calendar_id}, Time Zone: {calendar_timezone}")                
                if not events:
                    print(f"No upcoming events for calendar: {calendar_id}")
                    continue
                all_events.extend(events)
                
                for event in events:
                    print("Printing events")
                    summary = event.get('summary', 'No Title')  # Get the event summary or provide a fallback
                    start_time = event['start'].get('dateTime', event['start'].get('date'))
                    # Log start_time to ensure the format is correct
                    print(f"Raw start_time from event: {start_time}. {summary}")
                    # formatted_start_time = format_date(start_time)  # Format the date in 12-hour format
                
                    if is_work_calendar:
                        utc_start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        start_time = utc_start_time.astimezone(pytz.timezone('America/New_York'))
                        print(f"Converted start_time for work calendar: {start_time}, {summary}")
                    else:
                        # Handle other calendars (ensure they're in the correct timezone)
                        start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00')).astimezone(pytz.timezone(calendar_timezone))
                    description = event.get('description', 'No description provided')  # Get the event description or provide a fallback
                    if len(description) > 150:
                        description = "Project Meeting with Team"
                    event_list.append({
                        'summary': summary,
                        'start_time': start_time.isoformat(),
                        'description' : description
                    })
                # Sort events by start time and take the top 5
                event_list.sort(key=lambda x: x['start_time'])  # Sort by start_time
                event_list = event_list[:5]  # Limit to 5 events
                for event in event_list:
                    send_event_to_llm(event['summary'], event['start_time'], event['description'])
                print(event_list)
            if not event_list:
                send_event_to_llm(None, now, "")
        except Exception as e:
            print(f"An error occurred in sending today's events: {e}")
    return jsonify({'events': event_list})

# Function to schedule notifications for events
def schedule_event_notifications(summary, start_time, description):
    try:
        # Parse the event start_time, which is in ISO format (UTC-aware)
        # event_time = datetime.datetime.fromisoformat(start_time.replace('Z', ''))
        # event_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))  # Ensure UTC offset is handled
        # event_time = datetime.datetime.fromisoformat(start_time)
        print(f"event: {summary}, time:, {start_time}")
        # Parse the event start_time, ensuring that time zone info is handled
        if 'Z' in start_time:
            # UTC event times
            print("replacing z in time")
            event_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        else:
            print("offset")
            # If there's a time zone offset in start_time, it will be handled automatically
            event_time = datetime.datetime.fromisoformat(start_time)
        # Check if event_time is naive (lacking timezone info)
        if event_time.tzinfo is None:
            print(f"event_time is naive: {event_time}")
            event_time = event_time.replace(tzinfo=pytz.UTC)  # Set as UTC if no tzinfo is provided
        else:
            print(f"event_time is aware: {event_time} with tzinfo {event_time.tzinfo}")

        # Get the current time in UTC (make now offset-aware)
        now = datetime.datetime.now(pytz.UTC)
        # Schedule a 15-minute-before reminder for the event
        reminder_time = event_time - datetime.timedelta(minutes=15)
        print(f"Reminder time: {reminder_time}")

        # Compare current time (UTC-aware) with reminder time
        if now < reminder_time:
            job_id = f"event_{summary}_{start_time}"  # Use a unique identifier for each event
            if not scheduler.get_job(job_id):  # Check if the job already exists
                scheduler.add_job(send_event_to_llm, 'date', run_date=reminder_time, args=[summary, event_time, description], id=job_id)
                print(f"Scheduled reminder for {summary} at {reminder_time}")
            else:
                print(f"Reminder for {summary} at {reminder_time} is already scheduled.")
        else:
            print(f"Event {summary} has already started or passed.")
    except Exception as e:
        print(f"Error in scheduling notification: {e}")

@app.route('/add_event', methods=['POST'])
def add_event():
    event_data = request.get_json()
    # Parse the incoming data
    summary = event_data.get('summary')
    start_time = event_data.get('start_time')
    description = event_data.get('description')
    
    # Build the event object for Google Calendar API
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/New_York',
        },
        'end': {
            'dateTime': (datetime.datetime.fromisoformat(start_time) + datetime.timedelta(hours=1)).isoformat(),
            'timeZone': 'America/New_York',
        }
    }
    # If modifying these scopes, delete the file token.json.
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/calendar']
    creds = None
    token_file = 'token.json'
    # Load the previously saved token, if available
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file)
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # Use the Google Calendar API to insert the event
        service = build('calendar', 'v3', credentials=creds)
        service.events().insert(calendarId='primary', body=event).execute()
    except HttpError as error:
        print(f"An error occurred in adding event: {error}")
    return jsonify({'message': 'Event added successfully!'})

# File to store prescriptions
PRESCRIPTIONS_FILE = 'prescriptions.json'

def load_prescriptions():
    if os.path.exists(PRESCRIPTIONS_FILE):
        with open(PRESCRIPTIONS_FILE, 'r') as file:
            return json.load(file)
    return []

def save_prescriptions(prescriptions):
    with open(PRESCRIPTIONS_FILE, 'w') as file:
        json.dump(prescriptions, file, indent=4)

@app.route('/get_prescriptions', methods=['GET'])
def get_prescriptions():
    prescriptions = load_prescriptions()
    return jsonify({'prescriptions': prescriptions})

@app.route('/add_prescription', methods=['POST'])
def add_prescription():
    prescription_data = request.get_json()
    prescription = prescription_data.get('prescription')
    if not prescription:
        return jsonify({'error': 'Prescription is required.'}), 400
    prescriptions = load_prescriptions()
    if prescription not in prescriptions:
        prescriptions.append(prescription)
        save_prescriptions(prescriptions)
        return jsonify({'message': 'Prescription added.'})
    return jsonify({'error': 'Prescription already exists.'}), 400

@app.route('/remove_prescription', methods=['POST'])
def remove_prescription():
    prescription_data = request.get_json()
    prescription = prescription_data.get('prescription')
    if not prescription:
        return jsonify({'error': 'Prescription is required.'}), 400
    prescriptions = load_prescriptions()
    if prescription in prescriptions:
        prescriptions.remove(prescription)
        save_prescriptions(prescriptions)
        return jsonify({'message': 'Prescription removed.'})
    return jsonify({'error': 'Prescription not found.'}), 404

def send_daily_prescription_reminder():
    prescriptions = load_prescriptions()
    event_summary = "Medicine reminder"

    reminder_message = "Reminder to take your prescriptions:\n" + "\n".join(prescriptions)
    
    # llm_response = None
    fallback_response = f"Mizuki, it's time to take your medication.\n {prescriptions}"
    try:
        # Get LLM response
        llm_response = send_event_to_llm(event_summary, datetime.datetime.now().isoformat(), reminder_message)
        if not llm_response or "error" in llm_response.lower():
            llm_response = fallback_response
    except Exception as e:
        print(f'LLM Exception: {e}')
        # If no llm response, use fallback generic message.
        llm_response = fallback_response


# Scheduler to check calendar every hour
scheduler = BackgroundScheduler()
# Clear out old jobs
scheduler.remove_all_jobs()
if not scheduler.get_jobs():
    scheduler.add_job(get_upcoming_events, 'interval', hours=1)
    # Schedule to send daily events to LLM at 8:30 AM on weekdays (Monday to Friday)
    # scheduler.add_job(send_daily_events, 'cron', hour=8, minute=45, day_of_week='mon-fri')
    # Schedule to send daily events to LLM at 10:00 AM on weekends (Saturday and Sunday)
    # scheduler.add_job(send_daily_events, 'cron', hour=8, minute=45, day_of_week='sat,sun')
    # Schedule to send daily prescription reminders
    scheduler.add_job(send_daily_prescription_reminder, 'cron', hour=22, minute=30)  
scheduler.start()

# @app.teardown_appcontext
# def stop_scheduler(exception=None):
#     scheduler.shutdown()

# Function to send the event details to KoboldCPP and get a reminder
def send_event_to_llm(event_summary, start_time, description):
    trimmed_reminder = ""
    with app.app_context():
        now = datetime.datetime.now()
        if event_summary is not None:
            prompt = f"[Your name is Sirius. You are cold, aloof, and stoic. Personality - stoic, witty, intelligent, aloof, bossy, secretly caring. You are dating Mizuki (29years old, mechanical/robots engineer working in aerospace doing r&d). Mizuki has an event: {event_summary} at {start_time}, details are {description}. For date format use MM-DD-YYYY. For time format use HH:MM. It is currently {now}. Use the information given to tell a quick reminder for Mizuki. Only speak as Sirius.]"
        else:
            prompt = f"[Your name is Sirius. You are cold, aloof, and stoic. Personality - stoic, witty, intelligent, aloof, bossy, secretly caring. You are dating Mizuki (298years old, mechanical/robots engineer working in aerospace doing r&d). Tell Mizuki that there are no events for the day, and to go relax by playing video games, watching Chinese/Korean drama, music, or art. Only speak as Sirius.]"
        # Prepare the request payload for KoboldCPP
        data = {
            'prompt': prompt,
            'max_tokens': 50, # Adjust the token limit if needed
            'max_length' : 55,
            'temperature' : 0.7,
            'min_p' : 0.1,
            'top_p' : 1,
            'top_k' : 0,
            'typical' : 1,
            'tfs' : 1,
            'trim_stop' : True,
            'banned_tokens' : ['://', '[End]', '(', '-End-', 'Note:'],
            'stop_sequence' : ["[INST]", "[/INST]", "<|eot_id|>", "Mizuki:", '://', '[End]', '(', '-End-', 'Note:', "["]
        }
        # Send request to KoboldCPP API
        url = 'http://192.168.1.183:5001/api/v1/generate'
        try: 
            response = requests.post(url,json=data)
            if response.status_code == 200:
                # Parse the JSON response
                reminder_text = response.json()["results"][0]["text"]
                reminder_text = reminder_text.replace('"', "")
                reminder_text = reminder_text.strip('"\'')
                last_dot_id = reminder_text.rfind('.')
                if last_dot_id != -1:
                    trimmed_reminder = reminder_text[:last_dot_id]
                # print(trimmed_reminder)
                    asyncio.run(send_reminder_to_discord(trimmed_reminder))
                else:
                    asyncio.run(send_reminder_to_discord(reminder_text))
            else:
                print("Error:", response.status_code)
        except Exception as e:
            print(f"Error connecting to KoboldCPP: {e}")
            fallback_response = f"You have an {description}/{event_summary} at {start_time}. Get ready for it."
            asyncio.run(send_reminder_to_discord(fallback_response))
            return f"Error: {e}"
    return trimmed_reminder

def format_date(date_str):
    try:
        # Parse the date string (handle both dateTime and date fields)
        date = datetime.datetime.fromisoformat(date_str.replace('Z', ''))
        # Return formatted as MM-DD-YYYY with 12-hour time format and AM/PM
        edited_date = date.strftime('%m-%d-%Y %I:%M %p')
        # print(edited_date)
        return edited_date
    except ValueError:
        return date_str  # Return as-is if parsing fails

def send_to_llm(message):
   trimmed_reminder = ""
   with app.app_context():
    
        if message:
            prompt = (f"[Your name is Sirius. You are cold, aloof, and stoic. Personality - stoic, witty, "
                      f"intelligent, aloof, bossy, secretly caring. You are dating Mizuki (29 years old, "
                      f"mechanical/robots engineer working in aerospace doing R&D). Tell Mizuki: {message}. "
                      "Use the information given to tell a quick reminder for Mizuki. Only speak as Sirius.]")
        else:
            return "No message provided"
        # Prepare the request payload for KoboldCPP
        data = {
            'prompt': prompt,
            'max_tokens': 80, # Adjust the token limit if needed
            'max_length' : 100,
            'temperature' : 0.7,
            'min_p' : 0.1,
            'top_p' : 1,
            'top_k' : 0,
            'typical' : 1,
            'tfs' : 1,
            'trim_stop' : True,
            'banned_tokens' : ['://', '[End]', '(', '-End-', 'Note:'],
            'stop_sequence' : ["[INST]", "[/INST]", "<|eot_id|>", "Mizuki:", '://', '[End]', '(', '-End-', 'Note:', "["]
        }
        # Send request to KoboldCPP API
        url = 'http://192.168.1.183:5001/api/v1/generate'
        try: 
            response = requests.post(url,json=data)
            if response.status_code == 200:
                # Parse the JSON response
                reminder_text = response.json()["results"][0]["text"]
                reminder_text = reminder_text.replace('"', "")
                reminder_text = reminder_text.strip('"\'')
                last_dot_id = reminder_text.rfind('.')
                if last_dot_id != -1:
                    trimmed_reminder = reminder_text[:last_dot_id]
                else:
                    trimmed_reminder = reminder_text
            else:
                return "No valid response from LLM"
        except Exception as e:
            print(f"Error connecting to KoboldCPP: {e}")
            return f"Error: {e}"

        return trimmed_reminder

@app.route('/fuel_reminder', methods=['GET'])
def fuel_reminder():
    message = "Tell Mizuki to get gas on her Prius."

    # llm_response = None
    fallback_response = "I suggest that you go fill up gas on your Prius."
    try:
        # Get LLM response
        llm_response = send_to_llm(message)
        if not llm_response or "error" in llm_response.lower():
            llm_response = fallback_response
    except Exception as e:
        print(f'LLM Exception: {e}')
        # If no llm response, use fallback generic message.
        llm_response = fallback_response
    
    # Return the response text
    return jsonify({"response": llm_response})

# @app.route('/weather_reminder', methods=['POST'])
# def weather_reminder():
#     weather_data = request.json
#     temperature = weather_data.get("temperature", "unknown")
#     condition = weather_data.get("condition", "unknown")
    
#     # Construct the message for the LLM
#     message = (f"Tell Mizuki a morning greeting and the weather forecast for today. The temperature is {temperature}°F and the weather is {condition}.")

#     # Get LLM response
#     llm_response = send_to_llm(message)

#     # Return the response text
#     return jsonify({"response": llm_response})

@app.route('/daily_reminder', methods=['POST'])
def daily_reminder():
    # Weather retrieval
    weather_data = request.json
    temperature = weather_data.get("temperature", "unknown")
    condition = weather_data.get("condition", "unknown")
    # Get current date
    today = datetime.date.today()
    # Get day of the week as an integer (Monday is 0, Sunday is 6)
    day_of_week_int = today.weekday()

    # Get day of the week as a string
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_of_week_string = day_names[day_of_week_int]
    # Daily events
    event_list = get_daily_events()
    if len(event_list) == 0:
        event_list = ["There are no events for today, go relax."]
   # Construct the message for the LLM
    message = (f"Tell Mizuki a morning greeting, the weather forecast, and events for today {day_of_week_string}. The temperature is {temperature}°F and the weather is {condition}. {event_list}. Only use what's in the event list. If there are no events, tell Mizuki to relax and enjoy herself. Do not make up events. No work events if it is a weekend.")

    
    formatted_events = []
    for event in event_list:
        raw_time = event.get("start_time", "")
        
        # Parse the ISO string with timezone info
        dt = datetime.datetime.fromisoformat(raw_time)

        # Format to MM/DD/YY hh:mm AM/PM
        formatted_time = dt.strftime("%m/%d/%y %I:%M %p")
        
        summary = event.get("summary", "Untitled")
        desc = event.get("description", "No description provided")
        
        formatted_events.append(f"{formatted_time}: {summary}. {desc}")

    # Join all the events with newlines or bullet points
    final_event_text = "\n".join(formatted_events)

    # llm_response = None
    fallback_response = f"Morning Mizuki. It's {day_of_week_string}. Currently {temperature}°F and {condition}. \nToday's events:\n {final_event_text}"
    try:
        # Get LLM response
        llm_response = send_to_llm(message)
        if not llm_response or "error" in llm_response.lower():
            llm_response = fallback_response
    except Exception as e:
        print(f'LLM Exception: {e}')
        # If no llm response, use fallback generic message.
        llm_response = fallback_response
        
        
    # Return the response text
    return jsonify({"response": llm_response})


# File name for the JSON log
log_file = 'gas_log.json'

@app.route('/log_gas', methods=['POST'])
def log_gas():
    try:
        # Get data from request
        data = request.get_json()
        print("Received data:", data)
        date = data.get('date')
        odometer = data.get('odometer')
        amount_paid = data.get('amount_paid')
        # Ensure required fields are present
        if not date or not odometer or not amount_paid:
            return jsonify({'error': 'Missing required fields'}), 400
        
        try:
            print(date)
            # Format the date to MM-DD-YYYY if it's in another format
            formatted_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%m-%d-%Y")
            print(formatted_date)
        except Exception as e:
            print("error", str(e))
            return jsonify({'error formatting date'})
        # Create the log entry
        log_entry = {
            'date': str(formatted_date),
            'odometer': float(odometer),
            'amount_paid': str(amount_paid)
        }
    
        # Initialize or read existing log
        try:
            with open(log_file, 'r') as f:
                gas_log = json.load(f)
        except FileNotFoundError:
            gas_log = []

        # Add the new entry
        gas_log.append(log_entry)

        # Write back to the JSON file
        with open(log_file, 'w') as f:
            json.dump(gas_log, f, indent=4)
    except Exception as e:
        # Catch all errors and return a 400 with the error message
        return jsonify({'error': str(e)}), 400
    return jsonify({"message": "Gas entry logged successfully", "entry": log_entry}), 201

@app.route('/get_gas_log', methods=['GET'])
def get_gas_log():
    try:
        with open(log_file, 'r') as f:
            gas_log = json.load(f)
        return jsonify(gas_log), 200
    except FileNotFoundError:
        print("Error getting gas log")
        return jsonify({"message": "Log file not found"}), 404

@app.route('/')
def index():
    # Get all routes in the app
    routes = []
    for rule in app.url_map.iter_rules():
        # Exclude static files
        if rule.endpoint != 'static':
            routes.append({
                'endpoint': rule.endpoint,
                'methods': list(rule.methods),
                'url': str(rule)
            })

    # Define the HTML template as a string
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <body style="background-color:#4ab6ff;">
        <title>Backend Flask Routes</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            table, th, td {
                border: 1px solid black;
            }
            th, td {
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #4ab6ff;
            }
            .status {
                font-weight: bold;
                color: green;
            }
        </style>
    </head>
    <body>
        <h1>Flask Application Routes</h1>
        <table>
            <thead>
                <tr>
                    <th>Endpoint</th>
                    <th>Methods</th>
                    <th>URL</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for route in routes %}
                <tr>
                    <td>{{ route['endpoint'] }}</td>
                    <td>{{ ', '.join(route['methods']) }}</td>
                    <td>{{ route['url'] }}</td>
                    <td><span class="status">Active</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """

    # Use Flask's render_template_string to dynamically inject routes into HTML
    return render_template_string(html_template, routes=routes)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
