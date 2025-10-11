from flask import Blueprint, jsonify, request
from calendar_auth import get_calendar_service
import datetime, pytz, time
from googleapiclient.discovery import build
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError
from backend.utils import send_event_to_llm
from backend.scheduler import scheduler

calendar_bp = Blueprint('calendar', __name__)

# Fetch upcoming events from Google Calendar
@calendar_bp.route('/get_upcoming_events')
def get_upcoming_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    # Create a list of simplified event details
    event_list = []
    current_time = time.time()
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
        # print(f"event: {summary}, time:, {start_time}")
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
        #print(f"Reminder time: {reminder_time}")

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

@calendar_bp.route('/add_event', methods=['POST'])
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

