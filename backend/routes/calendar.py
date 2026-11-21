from flask import Blueprint, jsonify, request
from calendar_auth import get_calendar_service
import datetime, pytz, time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from backend.utils import generate_daily_briefing, send_event_to_llm
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
                print("Scheduled event: ", event)
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
        now = datetime.datetime.now(pytz.timezone('America/Los_Angeles')).isoformat()  # Current time in America/New_York ## WORKING
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
        if event_time <= now:
            print(f"Event {summary} has already started or passed.")
            return

        # Schedule a 15-minute-before reminder for the event
        reminder_time = event_time - datetime.timedelta(minutes=15)
        run_time = max(now, reminder_time)
        job_id = f"event_{summary}_{start_time}"  # Use a unique identifier for each event
        if not scheduler.get_job(job_id):  # Check if the job already exists
            scheduler.add_job(send_event_to_llm, 'date', run_date=run_time, args=[summary, event_time, description], id=job_id)
            if run_time == now and reminder_time < now:
                print(f"Reminder time passed; sending reminder for {summary} immediately.")
            else:
                print(f"Scheduled reminder for {summary} at {run_time}")
        else:
            print(f"Reminder for {summary} at {run_time} is already scheduled.")
    except Exception as e:
        print(f"Error in scheduling notification: {e}")

@calendar_bp.route('/add_event', methods=['POST'])
def add_event():
    event_data = request.get_json(silent=True)
    if not isinstance(event_data, dict):
        return jsonify({"error": "A JSON event object is required."}), 400

    summary = event_data.get("summary")
    start_time = event_data.get("start_time")
    if not isinstance(summary, str) or not summary.strip():
        return jsonify({"error": "Event summary is required."}), 400
    if not isinstance(start_time, str) or not start_time.strip():
        return jsonify({"error": "Event start_time is required."}), 400
    try:
        event_start = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "start_time must be an ISO 8601 date/time."}), 400

    local_timezone = pytz.timezone(LOCAL_TZ)
    if event_start.tzinfo is None:
        event_start = local_timezone.localize(event_start)
    else:
        event_start = event_start.astimezone(local_timezone)
    event_end = event_start + datetime.timedelta(hours=1)
    event = {
        "summary": summary.strip(),
        "description": str(event_data.get("description") or ""),
        "start": {"dateTime": event_start.isoformat(), "timeZone": LOCAL_TZ},
        "end": {"dateTime": event_end.isoformat(), "timeZone": LOCAL_TZ},
    }
    try:
        service = build("calendar", "v3", credentials=get_calendar_service())
        created_event = service.events().insert(calendarId="primary", body=event).execute()
    except HttpError as error:
        print(f"Google Calendar rejected event creation: {error}")
        status = getattr(error.resp, "status", 502)
        return jsonify({"error": "Google Calendar rejected the event.", "details": str(error)}), status
    return jsonify({"message": "Event added successfully.", "event_id": created_event.get("id")}), 201


# Daily reminders
@calendar_bp.route('/daily_reminder', methods=['POST'])
def daily_reminder():
    weather_data = request.get_json(silent=True) or {}
    temperature = weather_data.get("temperature", "unknown")
    condition = weather_data.get("condition", "unknown")
    events = get_daily_events()
    response = generate_daily_briefing(temperature, condition, events)
    return jsonify({"response": response})

# ---------------------------------------------------------------------------
# PASTE THIS AT THE BOTTOM OF backend/calendar.py
#
# Adds GET /events?day=today|tomorrow|next_7_days
# Used by calendar_tool.py so the CODE27 can answer "what's on my calendar?".
# Uses the imports calendar.py already has (datetime, pytz, build, request,
# jsonify, get_calendar_service, calendar_bp).
# ---------------------------------------------------------------------------
import re

LOCAL_TZ = "America/Los_Angeles"   # your real local time zone (the rest of calendar.py still says America/New_York)
MAX_EVENTS = 15
EVENT_DAYS = ("today", "tomorrow", "next_7_days")


def _day_window(day, tz, now=None):
    """Return (start, end, first_date) for the request. start/end are tz-aware local midnights, end is exclusive."""
    now = (now or datetime.datetime.now(tz)).astimezone(tz)
    first = 1 if day == "tomorrow" else 0
    span = 7 if day == "next_7_days" else 1
    first_date = now.date() + datetime.timedelta(days=first)
    midnight = lambda d: tz.localize(datetime.datetime.combine(d, datetime.time.min))
    return midnight(first_date), midnight(first_date + datetime.timedelta(days=span)), first_date


def _clip(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def _normalize_event(ev, tz, window_start, window_end):
    """Google event -> (sort_key, small dict).
    Returns None for events you declined or that fall outside your midnight-to-midnight window."""
    if any(a.get("self") and a.get("responseStatus") == "declined" for a in ev.get("attendees", [])):
        return None
    start, end = ev.get("start", {}), ev.get("end", {})
    if "date" in start:  # all-day event (end date is exclusive)
        midnight = lambda d: tz.localize(datetime.datetime.combine(datetime.date.fromisoformat(d), datetime.time.min))
        s = midnight(start["date"])
        e = midnight(end["date"]) if "date" in end else s + datetime.timedelta(days=1)
        out = {"date": start["date"], "start": "All day", "end": "", "all_day": True}
    else:
        s = datetime.datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone(tz)
        e = datetime.datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00")).astimezone(tz)
        out = {"date": s.strftime("%Y-%m-%d"), "start": _clock(s), "end": _clock(e), "all_day": False}
    # Google decides which all-day events match using the calendar's own time zone, which may not be
    # yours (e.g. still Eastern), so tomorrow's all-day events can leak into "today". Re-check here.
    if s >= window_end or (e <= window_start and s < window_start):
        return None
    sort_key = s
    description = re.sub(r"<[^>]+>", " ", ev.get("description") or "")  # Google descriptions can contain HTML
    out["title"] = _clip(ev.get("summary") or "No title", 80)
    # Long descriptions are usually meeting-invite boilerplate, so skip them.
    out["description"] = _clip(description, 120) if len(description) <= 150 else ""
    return sort_key, out


@calendar_bp.route("/events")
def events_for_day():
    day = request.args.get("day", "today")
    if day not in EVENT_DAYS:
        return jsonify({"error": "day must be one of: " + ", ".join(EVENT_DAYS)}), 400
    tz = pytz.timezone(LOCAL_TZ)
    start, end, first_date = _day_window(day, tz)
    found, seen = [], set()
    try:
        service = build("calendar", "v3", credentials=get_calendar_service())
        for cal in service.calendarList().list().execute().get("items", []):
            result = service.events().list(
                calendarId=cal["id"], timeMin=start.isoformat(), timeMax=end.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=50,
            ).execute()
            for ev in result.get("items", []):
                item = _normalize_event(ev, tz, start, end)
                if item is None:
                    continue
                key = (item[0], item[1]["title"])  # same event shared across calendars
                if key not in seen:
                    seen.add(key)
                    found.append(item)
    except Exception as error:
        print(f"An error occurred in /events: {error}")
        return jsonify({"error": str(error)}), 502
    found.sort(key=lambda pair: pair[0])
    return jsonify({
        "timezone": LOCAL_TZ,
        "day": day,
        "date": first_date.isoformat(),
        "events": [item for _, item in found][:MAX_EVENTS],
        "truncated": len(found) > MAX_EVENTS,
    })