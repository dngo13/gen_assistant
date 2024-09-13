from flask import Flask, jsonify
from googleapiclient.discovery import build
import datetime
from calendar_auth import get_calendar_service

app = Flask(__name__)

# # Fetch upcoming events from Google Calendar
@app.route('/get_upcoming_events')
def get_upcoming_events():
    # Get Google Calendar service
    creds = get_calendar_service()
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        # Get events starting from now to the next day
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print("Getting the upcoming 10 events")
        # tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + '-5'
        
        # events_result = service.events().list(
        #     calendarId='primary', timeMin=now, timeMax=tomorrow,
        #     maxResults=10, singleEvents=True, orderBy='startTime').execute()
        
        events_result = (
            service.events()
            .list(
                calendarId='primary', 
                timeMin=now,
                maxResults=10, 
                singleEvents=True, orderBy='startTime'
            )
            .execute()
        )
        events = events_result.get('items', [])
        if not events:
            print("No upcoming events.")
            return
        
        # Create a list of simplified event details
        event_list = []
        for event in events:
            start_time = event['start'].get('dateTime', event['start'].get('date'))
            event_list.append({
                'summary': event['summary'],
                'start_time': start_time
            })
    except HttpError as error:
        print(f"An error occurred: {error}")

    return jsonify({'events': event_list})

# Basic route to test the server
@app.route('/')
def index():
    return jsonify({"message": "Flask app is running!"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
