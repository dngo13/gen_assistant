from flask import Flask, jsonify
from googleapiclient.discovery import build
import datetime
from calendar_auth import get_calendar_service
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import pytz
from bot_run import send_reminder_to_discord # Import the send function from the bot file

app = Flask(__name__)

# Fetch upcoming events from Google Calendar
@app.route('/get_upcoming_events')
def get_upcoming_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        # Get events starting from now to the next day
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print("Getting the upcoming 5 events")
      
        events_result = (
            service.events()
            .list(
                calendarId='primary', 
                timeMin=now,
                maxResults=5, 
                singleEvents=True, orderBy='startTime'
            )
            .execute()
        )
        events = events_result.get('items', [])
        if not events:
            print("No upcoming events.")
            return jsonify({"message": "No upcoming events."})
        print(events)
        # Create a list of simplified event details
        event_list = []
        for event in events:
            # print("Printing events")
            summary = event.get('summary', 'No Title')  # Get the event summary or provide a fallback
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            formatted_start_time = format_date(start_time)  # Format the date in 12-hour format
            description = event.get('description', 'No description provided')  # Get the event description or provide a fallback
            
            event_list.append({
                'summary': summary,
                'start_time': formatted_start_time,
                'description' : description
            })
            schedule_event_notifications(summary, start_time, description)
    except Exception as e:
        print(f"An error occurred: {e}")
    return jsonify({'events': event_list})

def send_daily_events():
    creds = get_calendar_service()
    try:
        service = build('calendar', 'v3', credentials=creds)

        # Get events starting from today 12:01 AM to the end of the day
        now = datetime.datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_of_day = (datetime.datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)).isoformat() + 'Z'
        
        events_result = (
            service.events()
            .list(
                calendarId='primary',
                timeMin=now,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy='startTime'
            )
            .execute()
        )
        events = events_result.get('items', [])
        if not events:
            print("No events for today.")
            send_event_to_llm(None, now, "")
            return

        # Send all events happening today to the LLM
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            formatted_start_time = format_date(start_time)  # Format the date
            description = event.get('description', 'No description provided')  # Get the event description
            summary = event.get('summary', 'No Title')  # Get the event summary
            
            # Notify LLM about today's events
            send_event_to_llm(summary, formatted_start_time, description)
    
    except Exception as e:
        print(f"Error fetching today's events: {e}")

# Function to schedule notifications for events
def schedule_event_notifications(summary, start_time, description):
    # Parse the event start_time, which is in ISO format (UTC-aware)
    event_time = datetime.datetime.fromisoformat(start_time.replace('Z', ''))

    # Get the current time in UTC (make now offset-aware)
    now = datetime.datetime.now(pytz.UTC)

    # Schedule a 15-minute-before reminder for the event
    reminder_time = event_time - datetime.timedelta(minutes=15)
    print(f"Reminder time: {reminder_time}")

    # Compare current time (UTC-aware) with reminder time
    if now < reminder_time:
        # Schedule the job if the reminder time is in the future
        scheduler.add_job(send_event_to_llm, 'date', run_date=reminder_time, args=[summary, event_time, description])
        print(f"Scheduled reminder for {summary} at {reminder_time}")
    else:
        print(f"Reminder for {summary} not scheduled because it's past the reminder time.")

# Scheduler to check calendar every hour
scheduler = BackgroundScheduler()
# Clear out old jobs
scheduler.remove_all_jobs()
scheduler.add_job(get_upcoming_events, 'interval', hours=1)
# Schedule to send daily events to LLM at 8:30 AM on weekdays (Monday to Friday)
scheduler.add_job(send_daily_events, 'cron', hour=8, minute=30, day_of_week='mon-fri')

# Schedule to send daily events to LLM at 10:00 AM on weekends (Saturday and Sunday)
scheduler.add_job(send_daily_events, 'cron', hour=10, minute=00, day_of_week='sat,sun')
scheduler.start()

# @app.teardown_appcontext
# def stop_scheduler(exception=None):
#     scheduler.shutdown()

# Function to send the event details to KoboldCPP and get a reminder
def send_event_to_llm(event_summary, start_time, description):
    now = datetime.datetime.now()
    if event_summary is not None:
        prompt = f"Your name is Sirius. You are cold, aloof, and stoic. Personality - stoic, witty, intelligent, aloof, bossy, secretly caring. You are dating Mizuki. Mizuki has an event: {event_summary} at {start_time}, details are {description}. For date format use MM-DD-YYYY. For time format use HH:MM. It is currently {now}. Use the information given to tell a quick reminder for Mizuki. Only speak as Sirius."
    else:
        prompt = f"Your name is Sirius. You are cold, aloof, and stoic. Personality - stoic, witty, intelligent, aloof, bossy, secretly caring. You are dating Mizuki. Tell Mizuki that there are no events for the day, and to go relax by playing video games or watching anime/drama. Only speak as Sirius."
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
        'stop_sequence' : ["[INST]", "[/INST]", "<|eot_id|>", "Mizuki:", '://', '[End]', '(', '-End-', 'Note:']
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
            print("Error:", response.status_code)
    except Exception as e:
        print(f"Error connecting to KoboldCPP: {e}")

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

# Basic route to test the server
@app.route('/')
def index():
    return jsonify({"message": "Flask app is running!"})


if __name__ == '__main__':
    with app.app_context():
        get_upcoming_events()
        app.run(debug=True, port=5000)
