"""
This module has general utility functions that's shared in the backend.
Such as send_event_to_llm and send_to_llm.
"""
import datetime
import requests
import asyncio
from bot_run import send_reminder_to_discord

# Function to send the event details to KoboldCPP and get a reminder
def send_event_to_llm(event_summary, start_time, description):
    trimmed_reminder = ""

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
