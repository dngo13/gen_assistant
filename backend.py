from flask import Flask, jsonify
from googleapiclient.discovery import build
import datetime
from calendar_auth import get_calendar_service
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio

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
        # now = datetime.datetime.now()
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
        
        # Create a list of simplified event details
        event_list = []
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            description = event.get('description', 'No description provided')  # Get the event description or provide a fallback
            summary = event.get('summary', 'No Title')  # Get the event summary or provide a fallback
            
            event_list.append({
                'summary': summary,
                'start_time': start_time,
                'description' : description
            })
            send_event_to_llm(summary, start_time, description)
    except Exception as e:
        print(f"An error occurred: {e}")
    # send_event_to_llm(event_list)
    return jsonify({'events': event_list})

# Scheduler to check calendar every hour
scheduler = BackgroundScheduler()
scheduler.add_job(get_upcoming_events, 'interval', hours=1)
scheduler.start()

# Function to send the event details to KoboldCPP and get a reminder
def send_event_to_llm(event_summary, start_time, description):
    prompt = f"Your name is Sirius. You are robotics engineer that works in the space industry. You are cold, aloof, and stoic. Comes off as rude, blunt, and direct with lack of words, and prefers showing actions. Has a dominant and bossy side. personality - tough exterior, stoic, witty, intelligent, aloof, cold, distant, bullying, dominant, bossy, casual, blunt, secretly caring. You are dating Mizuki. Mizuki has an event: {event_summary} at {start_time}, details are {description}. Use the information given to tell a quick reminder (upcoming events) for Mizuki. Only speak as Sirius."
    
    # Prepare the request payload for KoboldCPP
    data = {
        'prompt': prompt,
        'max_tokens': 20, # Adjust the token limit if needed
        'max_length' : 50,
        'temperature' : 0.9,
        'min_p' : 0.1,
        'top_p' : 1,
        'top_k' : 0,
        'typical' : 1,
        'tfs' : 1
    }
    # Send request to KoboldCPP API
    url = 'http://192.168.1.183:5001/api/v1/generate'
    try: 
        response = requests.post(url,json=data)
        print(response.json()["results"][0]["text"])
        if response.status_code == 200:
            # Parse the JSON response
            reminder_text = response.json()["results"][0]["text"]
            # print(type(reminder_text))
            # print(reminder_text)
            asyncio.run(send_reminder_to_discord(reminder_text))
        else:
            print("Error:", response.status_code)
    except Exception as e:
        print(f"Error connecting to KoboldCPP: {e}")

# Basic route to test the server
@app.route('/')
def index():
    return jsonify({"message": "Flask app is running!"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
