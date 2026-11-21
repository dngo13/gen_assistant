"""Shared backend helpers for CODE27 reminders and KoboldCpp responses."""
import datetime
import requests
import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from CODE27.integrations.local_api import LocalAPI
from bot_run import send_reminder_to_discord

load_dotenv()
_code27_api = None

def get_code27_api():
    global _code27_api
    if _code27_api is not None:
        return _code27_api

    device_url = os.getenv("CODE27_DEVICE_URL", "").strip()
    credentials_path = Path(os.getenv(
        "CODE27_CREDENTIALS_PATH",
        "CODE27/integrations/credentials_permanent.json",
    ))
    if not device_url:
        raise RuntimeError("Set CODE27_DEVICE_URL to use CODE27 event reminders.")
    if not credentials_path.is_file():
        raise RuntimeError(f"CODE27 credentials not found: {credentials_path}")
    with credentials_path.open("r", encoding="utf-8") as credentials_file:
        credentials = json.load(credentials_file)
    if not isinstance(credentials, dict) or not credentials.get("local_secret"):
        raise ValueError(f"CODE27 credentials file is invalid: {credentials_path}")

    _code27_api = LocalAPI(device_url, credentials)
    return _code27_api

# Generate a spoken CODE27 reminder and post the same text to Discord.
def send_event_to_llm(event_summary, start_time, description):
    now = datetime.datetime.now()
    if event_summary is not None:
        prompt = (
            f"Give Mizuki a brief spoken reminder about this calendar event: {event_summary} "
            f"at {start_time}. Details: {description}. It is currently {now}. "
            "State the event time clearly. Do not invent details. Only speak as Sirius."
        )
    else:
        prompt = (
            "Tell Mizuki there are no events scheduled today and suggest she relax. "
            "Only speak as Sirius."
        )

    try: 
        turn = get_code27_api().chat_turn(
            prompt,
            timeout=180,
            speech="device",
            retention="none",
            tools="none",
            interrupt=False,
        )
        reminder_text = turn.get("assistant_text", "").strip()
        if not reminder_text:
            raise RuntimeError("CODE27 completed the reminder without generating text.")
    except Exception as e:
        print(f"Error generating or speaking CODE27 event reminder: {e}")
        if event_summary is None:
            fallback_response = "There are no events scheduled today. Take some time to relax."
        else:
            fallback_response = f"Reminder: {event_summary} is at {start_time}. {description}".strip()
        asyncio.run(send_reminder_to_discord(fallback_response))
        return fallback_response

    try:
        asyncio.run(send_reminder_to_discord(reminder_text))
    except Exception as e:
        print(f"Failed to send CODE27 event reminder to Discord: {e}")
        return f"Error sending reminder to Discord: {e}"
    return reminder_text

# Sends prompt to LLM for a reply
def send_to_llm(message):
    trimmed_reminder = ""
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

# Formats date to MM-DD-YYYY with 12 hour time and am/pm
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
