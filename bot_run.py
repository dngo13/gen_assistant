import discord
from discord.ext import commands
from discord import app_commands
import requests
import asyncio
import datetime
import discord_webhook
from dotenv import load_dotenv
import os
import random
import json
import aiohttp
import re
import google.generativeai as genai
import websockets
import wave

# Discord setup
intents = discord.Intents.default()
intents.message_content = True

# Set command prefix
command_prefix='!'
bot = commands.Bot(command_prefix, intents=intents)
tree = bot.tree

# Chat settings
global CHAT_CHANNEL_ID # set with /setchat
CHAT_CHANNEL_ID = 1209696916590567575  # initialize
global chat_memory
chat_memory = []
# Keep track of the last bot message
last_bot_msg_id = None
global prompt
bot_responses = {}
CHAT_HISTORY_FILE = "bot_config/chat_history.json"
DEFAULT_CONTEXT_LIMIT = 8192 # fallback if KoboldCPP query fails

## TTS
from alltalk_tts_api import AllTalkAPI  # import the TTS class
tts_api = AllTalkAPI()
# Websocket for tts to browser
connected_clients = set()
# Flask backend URL settings
BACKEND_HOST_IP = "192.168.1.175"
BACKEND_HOST_PORT = 5000
BACKEND_URL = f"http://{BACKEND_HOST_IP}:{BACKEND_HOST_PORT}"

# Websearch
WEBSEARCH_KEYWORDS = [
    "search for", "look up", "find me", "tell me", "explain me", "can you", "how to", "how is", "how do you", "how do i",
    "ways to", "who is", "who are", "who was", "who were", "who did", "who's your", "what is", "what's", "what are",
    "what're", "what was", "what were", "what did", "what do", "where are", "where're", "where's", "where is",
    "how much", "definition of",
    "what happened", "why does", "why do", "why did", "why is", "why are", "why were", "when does", "when do",
    "when did", "when is", "when was", "when were", "how does", "meaning of", "can you", "could you"
]
# "where was", "where were", "where did", "where do", "where does", "where can",
# Create a Gemini GenerativeModel instance
gemini_model = genai.GenerativeModel('gemini-2.5-flash-lite') # Use gemini-pro-vision for image input

# KoboldCPP API URL
url = 'http://192.168.1.183:5001/api/v1/generate'

# Load jsons for model and character
def load_json_config(path, fallback={}):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Config Failed to load {path}: {e}")
        return fallback

def save_model_config(path, config):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

character_config = load_json_config("bot_config/character.json")

# Save chat history to JSON
def save_chat_history():
    try:
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ChatMemory] Failed to save history: {e}")

# Load chat history
def load_chat_history():
    try:
        if os.path.exists(CHAT_HISTORY_FILE):
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [(r, m) for r, m in data if isinstance(r, str) and isinstance(m, str)]
    except Exception as e:
        print(f"[ChatMemory] Failed to load history: {e}")
    return []

chat_memory = load_chat_history()
print(f"[ChatMemory] Loaded {len(chat_memory)} messages from disk.")

# Model config defaults (these are your given parameters)
default_model_config = {
    "max_context_length": 16384,
    "max_length": 30,
    "prompt": "",
    "quiet": False,
    "rep_pen": 1.1,
    "rep_pen_range": 831,
    "rep_pen_slope": 1,
    "temperature": 1.02,
    "tfs": 1,
    "top_a": 0,
    "top_k": 0,
    "top_p": 1,
    "typical_p": 1,
    "min_p": 0.1,
    "stop_sequence": ["User:", "Bot:"]
}

model_config = load_json_config("bot_config/model.json", default_model_config)

def trigger_websearch(message: str) -> str | None:
    msg_lower = message.lower()
    for kw in WEBSEARCH_KEYWORDS:
        if kw in msg_lower:
            # Optionally, extract the query after the keyword
            # For now, just use the whole message as the search query
            return message
    return None

def get_websearch_results(query: str) -> str:
    try:
        response = requests.post(
            "http://192.168.1.183:5001/api/extra/websearch",
            json={"q": query},
            timeout=10
        )
        if response.status_code == 200:
            results = response.json()
            # Format results for prompt injection
            formatted = "\n".join(
                f"{i+1}. {r['title']} - {r['url']}\n{r['desc']}\n"
                for i, r in enumerate(results)
            )
            print(f"Websearch results for '{query}':\n{formatted}\n")
            return f"Websearch results for '{query}':\n{formatted}\n"
        else:
            return "No websearch results found.\n"
    except Exception as e:
        print(f"[Websearch] Error: {e}")
        return "Websearch failed.\n"
    
def build_payload(chat_memory, websearch_text=None):
    """
    Build payload for KoboldCPP, including system block and proper Llama 3 token wrapping.
    """
    # print("chat history: " , chat_memory)
    payload = model_config.copy()
    now = datetime.datetime.now()
    current_datetime = now.strftime("%B %d, %Y %I:%M:%S %p")
    day_of_week = now.strftime("%A")

    # --- System block (built once per payload) ---
    system_text = (
        f"You are {character_config['name']}. "
        f"{character_config['description']} "
        f"Use the personality {character_config['personality']} to immerse yourself in your role. "
        "You are in a relationship with Mizuki, the user. Mizuki is a 29 year old Vietnamese girl, lives in Maryland, US. "
        "She is an opto-mechanical engineer that works in aerospace and robotics. Likes playing video games, watching anime, k-drama, and c-drama, reading. "
        "She enjoys spicy foods, all Asian cuisine and culture. Drinks iced Vietnamese coffee."
        "Hates the outdoors, sports, drinking alcohol. Has Grave's disease, allergies, asthma, restless legs syndrome"
        "She can be a workaholic and often feels inadequate as an engineer but tries to avoid overtime."
        f"Ensure you follow these rules. {character_config['behavior']}. "
        "Example output: <|start_header_id|>assistant<|end_header_id|>o.o whats wrong?<|eot_id|><|start_header_id|>assistant<|end_header_id|>-_-. time to go to work, here's ur coffee<|eot_id|>, <|start_header_id|>assistant<|end_header_id|>:D wooo time to play games together!<|eot_id|>"
    )

    prompt = f"<|start_header_id|>system<|end_header_id|>\n{system_text}\n<|eot_id|>"

    # Add chat history
    for role, msg in chat_memory:
        role_lower = role.lower()
        if role_lower not in ("user", "assistant"):
            continue
        prompt += f"<|start_header_id|>{role_lower}<|end_header_id|>\n{msg.strip()}\n<|eot_id|>"

    # Inject websearch results if provided
    if websearch_text:
        prompt += f"<|start_header_id|>system<|end_header_id|>\n{websearch_text}\n<|eot_id|>"

    authors_note = f"You are aware of the current time: {current_datetime}, {day_of_week} and the schedule of {character_config['schedule']}. Do not assume the user's habits (sleep, work, or meal times). Use the personality {character_config['personality']} to immerse yourself in your role. Ensure you follow these rules. {character_config['behavior']}."
    # Inject author's note if provided
    if authors_note:
        prompt += f"<|start_header_id|>system<|end_header_id|>\n{authors_note}\n<|eot_id|>"

    # Cue assistant to respond
    prompt += "<|start_header_id|>assistant<|end_header_id|>\n"

    payload["prompt"] = prompt
    return payload

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await bot.get_channel(1191949009405878314).send("Sirius is online")
    await tree.sync()
    # await bot.wait_until_ready()  # Wait until the bot is fully initialized

@bot.event
async def sync():
    await tree.sync()

# Slash command to manually pull Google Calendar events and send them to the Discord channel
@tree.command(name="get_events", description="List upcoming Google Calendar events")
async def get_events(interaction: discord.Interaction):
    await interaction.response.defer()  # Acknowledge the interaction
    try:
        # Pull events from the Flask backend
        events_url = f"{BACKEND_URL}/get_upcoming_events"
        response = requests.get(events_url)
                # await interaction.followup.send("Events retrieved successfully!")
        if response.status_code == 200:
            
            events = response.json().get('events', [])
            if events:
                # Format the events for better readability
                event_messages = []
                for event in events:
                    summary = event.get('summary', 'No Title')
                    start_time = event.get('start_time', 'No Time')
                    formatted_date = format_date(start_time)
                    description = event.get('description', 'No description provided')
                    event_messages.append(f"**Event:** {summary}\n**Start Time:** {formatted_date}\n**Description:** {description}")
                
                # Combine all events into a single message string
                combined_message = "\n".join(event_messages)
                print(combined_message)
                await interaction.followup.send(combined_message)
            else:
                await interaction.followup.send("No upcoming events.")
        else:
            await interaction.followup.send("Failed to get events.")

    except Exception as e:
        await interaction.followup.send("An error occurred")

def format_date(date_str):
    try:
        # Parse the date string (handle both dateTime and date fields)
        date = datetime.datetime.fromisoformat(date_str.replace('Z', ''))
        # Return formatted as MM-DD-YYYY with 12-hour time format and AM/PM
        edited_date = date.strftime('%m-%d-%Y %I:%M %p')
        return edited_date
    except ValueError:
        return date_str  # Return as-is if parsing fails

# Function to send a reminder directly to Discord (called from the backend)
@bot.event
async def send_reminder_to_discord(reminder):
    # Ensure the bot's cache is ready
    discord_webhook_url = 'https://discord.com/api/webhooks/1326011705276497980/VCcyd16UlOlrrk743uz2x0auFtUSNatDPT92_FAlTTWrxmTHOr9UHBlwF40NNmbK7Q5h'
    webhook = discord_webhook.DiscordWebhook(url=discord_webhook_url)
    ping_me = "<@119137826158673921>"
    msg = ping_me + reminder
    webhook.content = msg
    response = webhook.execute()
    # await message.channel.send(msg)

@tree.command(name='add_prescription', description='Add a new prescription')
@app_commands.describe(prescription="Prescription name and dose")
async def add_prescription(interaction: discord.Interaction, prescription: str):
    print("Adding prescription")
    response = requests.post(f'{BACKEND_URL}/add_prescription', json={'prescription': prescription})
    if response.status_code == 200:
        await interaction.response.send_message(f"Prescription '{prescription}' added.")
    else:
        await interaction.response.send_message(f"Error: {response.json().get('error')}")

@tree.command(name='remove_prescription', description='Remove a prescription')
@app_commands.describe(prescription="Prescription name and dose")
async def remove_prescription(interaction: discord.Interaction, prescription: str):
    print("Removing prescription.")
    response = requests.post(f'{BACKEND_URL}/remove_prescription', json={'prescription': prescription})
    if response.status_code == 200:
        await interaction.response.send_message(f"Prescription '{prescription}' removed.")
    else:
        await interaction.response.send_message(f"Error: {response.json().get('error')}")

@tree.command(name='get_prescriptions', description='List all prescriptions')
async def get_prescriptions(interaction: discord.Interaction):
    print("Getting prescriptions.")
    response = requests.get(f'{BACKEND_URL}/get_prescriptions')
    if response.status_code == 200:
        prescriptions = response.json().get('prescriptions', [])
        if prescriptions:
            await interaction.response.send_message("Current prescriptions:\n" + "\n".join(prescriptions))
        else:
            await interaction.response.send_message("No prescriptions found.")
    else:
        await interaction.response.send_message(f"Error: {response.json().get('error')}")

@tree.command(name='get_gas_log', description='Shows gas log for Prius')
async def get_gas_log(interaction: discord.Interaction):
    await interaction.response.defer()  # Acknowledge the interaction
    print("Pulling up gas log")
    response = requests.get(f'{BACKEND_URL}/get_gas_log')
    if response.status_code == 200:
        gas_log = response.json()  # Get the full gas log list
        if gas_log:
            # Format the gas log entries for the message
            log_entries = []
            for entry in gas_log:
                log_entries.append(f"Date: {entry['date']}, Odometer: {entry['odometer']}, Amount Paid: ${entry['amount_paid']}")
            await interaction.followup.send("Current Gas Log:\n" + "\n".join(log_entries))
        else:
            await interaction.followup.send("No gas entries found.")
    else:
        await interaction.followup.send(f"Error: {response.json().get('message', 'Unknown error')}")

# Get llm model parameters from json file
@tree.command(name="get_model_params", description="Shows current model parameters from backend")
async def get_model_params(interaction: discord.Interaction):
    await interaction.response.defer()  # acknowledge interaction

    try:
        response = requests.get(f"{BACKEND_URL}/get_model_params", timeout=5)
    except requests.RequestException as e:
        await interaction.followup.send(f"Could not reach backend: {e}", ephemeral=True)
        return

    if response.status_code == 200:
        model_params = response.json()
        if model_params:
            # Build a formatted list for Discord message
            formatted_lines = []
            for key, value in model_params.items():
                if isinstance(value, list):
                    value = ", ".join(str(i) for i in value)
                formatted_lines.append(f"{key}: {value}")
            
            # Discord message limit safety (2000 chars)
            formatted_output = "\n".join(formatted_lines)
            if len(formatted_output) > 1900:
                formatted_output = formatted_output[:1900] + "\n…(truncated)"

            await interaction.followup.send(f"**Current Model Parameters:**\n{formatted_output}")
        else:
            await interaction.followup.send("No model parameters found.")
    else:
        msg = response.json().get("message", "Unknown error")
        await interaction.followup.send(f"Error fetching model params: {msg}")

@tree.command(name="set_model_param", description="Set a parameter for the llm model.json file")
@app_commands.describe(
    param="The name of the model parameter to update",
    value="The new value for the parameter"
)
async def set_model_param(interaction: discord.Interaction, param: str, value: str):
    """Send a POST request to Flask to update model.json"""
    await interaction.response.defer(thinking=True)

    try:
        payload = {"param": param, "value": value}
        response = requests.post(f"{BACKEND_URL}/set_model_param", json=payload, timeout=5)

        if response.status_code == 200:
            msg = response.json().get("message", "Parameter updated successfully.")
            await interaction.followup.send(msg)
        elif response.status_code == 404:
            await interaction.followup.send(f"Parameter '{param}' not found.")
        else:
            await interaction.followup.send(f"Error updating parameter: {response.text}")

    except requests.exceptions.ConnectionError:
        await interaction.followup.send("Cannot reach backend Flask API.")
    except Exception as e:
        await interaction.followup.send(f"Unexpected error: {e}")

# Function to trim replies and remove unfinished sentence
def trim_to_last_sentence(text):
    import re
    # Find the last sentence-ending punctuation (., !, ?)
    matches = list(re.finditer(r'[.!?]', text))
    if matches:
        last = matches[-1].end()
        return text[:last].strip()
    return text.strip()

@bot.event
async def on_message(message):
    global last_bot_msg_id

    # Get the message content, make it lowercase
    msg_content: str = message.content.lower()
    # Prefix based commands
    if msg_content.startswith(command_prefix):
        msg_content = msg_content.replace(command_prefix,"")
        if message.author == bot.user:
            return
        match msg_content: 
            case "help":
                await message.channel.send('You need my help again? Tsk tsk. Here are the commands.\n ping, sync, get_events, add_event, get_prescriptions, add_prescription, remove_prescription, join, leave, clear')
            case "ping":
                await message.channel.send(f'Pong! {round(bot.latency * 1000)}ms')
            case "sync":
                await message.channel.send('Syncing commands')
            case "get_events":
                await message.channel.send('Getting events, please hold.')
                await get_events(message)
            case "get_prescriptions":
                await message.channel.send('Getting prescriptions, one sec.')
                await get_prescriptions(message)
            case "clear":
                chat_memory.clear()
                save_chat_history()
                await message.channel.send("Chat memory cleared.")
            case "abort":
                try:
                    response = requests.post("http://192.168.1.183:5001/api/extra/abort")
                    if response.status_code == 200:
                        await message.channel.send("Text generation aborted.")
                except Exception as e:
                    await message.channel.send(f"Error aborting generation: {e}")
                return
    # only process messages in the specified chat channel
    if CHAT_CHANNEL_ID != 0 and message.channel.id == CHAT_CHANNEL_ID:
        # Ignore message from bot or embeds
        if message.author == bot.user or message.embeds:
            return
        msg_content: str = message.content.lower()
        full_user_message_content = message.content # Store original for memory if no image

        image_caption = None
        # --- Image Processing with Gemini ---
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image'):
                    print(f"Detected image attachment: {attachment.filename}")
                    async with message.channel.typing():
                        try:
                            # Download the image using aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(attachment.url) as resp:
                                    resp.raise_for_status() # Raise an exception for bad status codes
                                    image_bytes = await resp.read()

                            # Prepare image for Gemini
                            image_part = {
                                'mime_type': attachment.content_type,
                                'data': image_bytes
                            }

                            # Generate caption using Gemini-Pro-Vision
                            print("Sending image to Gemini for captioning...")
                            gemini_response = await asyncio.to_thread(
                                gemini_model.generate_content,
                                [image_part, "Describe this image in detail."] # You can customize the prompt here
                            )
                            image_caption = gemini_response.text
                            print(f"Gemini caption: {image_caption}")

                            # Prepend the caption to the user's message or use it solely if no text
                            if message.content:
                                full_user_message_content = f"The user sent an image described as: \"{image_caption}\". Their message was: \"{message.content}\""
                            else:
                                full_user_message_content = f"The user sent an image described as: \"{image_caption}\"."
                            break # Only process the first image attachment
                        except Exception as e:
                            print(f"Error processing image with Gemini: {e}")
                            await message.channel.send(f"Sorry, I had trouble processing that image: {e}")
                            # If image processing fails, continue with original message content
                            full_user_message_content = message.content


        # Store conversation as logical roles, no tokens yet
        full_user_message_content = full_user_message_content.replace("**mizuki_sakai**:", "").strip()
        #print(full_user_message_content)
        chat_memory.append(("user", full_user_message_content))

        # Trim memory
        # total_chars = sum(len(msg) for _, msg in chat_memory)
        # while total_chars > CHAT_CONTEXT_LIMIT and len(chat_memory) > 1:
        #     chat_memory.pop(0)
        #     total_chars = sum(len(msg) for _, msg in chat_memory)
        #     save_chat_history()

        # --- Websearch trigger ---
        websearch_query = trigger_websearch(message.content)
        websearch_text = None
        if websearch_query:
            websearch_text = get_websearch_results(websearch_query)

        # Build payload with proper tokens and system block inside build_payload
        async with message.channel.typing():
            # payload = build_payload(chat_memory)
            reply = generate_reply(chat_memory, websearch_text=websearch_text)
            trimmed_reply = trim_to_last_sentence(reply)
        # Add assistant reply to memory
        chat_memory.append(("assistant", trimmed_reply))
        save_chat_history()

        bot_msg = await message.channel.send(trimmed_reply)
        save_chat_history()
        vc = message.guild.voice_client
        if vc and vc.is_connected():
            # Generate TTS for the reply
            tts_result = tts_api.generate_tts(
                text=trimmed_reply,
                character_voice="ash_island.wav",  # pick your desired voice
                language="en",
                output_file_name="discord_reply"
            )
            # Play TTS in VC
            if tts_result:
                await play_tts_in_vc(vc, tts_result)
            else:
                print("Failed to generate TTS")
        
        # Remove reactions from previous bot message
        if last_bot_msg_id:
            try:
                old_msg = await message.channel.fetch_message(last_bot_msg_id)
                await old_msg.clear_reactions()
            except discord.NotFound:
                pass  # message deleted
            except discord.Forbidden:
                pass  # no permission
            except discord.HTTPException:
                pass  # some other error
        
        # Add reactions
        await bot_msg.add_reaction("⬅️")
        await bot_msg.add_reaction("➡️")
        # Update last bot message
        last_bot_msg_id = bot_msg.id
        # Track variants for this message
        bot_responses[bot_msg.id] = {"alternatives": [reply], "index": 0}
       

# Slash command to add a new event to Google Calendar
@tree.command(name="add_event", description="Add a new event to Google Calendar")
@app_commands.describe(summary="Title of the event", start_time="Event start time (MM-DD-YYYY HH:MM AM/PM)", description="Event description")
async def add_event(interaction: discord.Interaction, summary: str, start_time: str, description: str):
    try:
        # Convert the start_time to the appropriate datetime format
        event_time = datetime.datetime.strptime(start_time, '%m-%d-%Y %I:%M %p')
        event_data = {
            'summary': summary,
            'start_time': event_time.isoformat(),
            'description': description
        }

        # Send the event data to the Flask backend to add it to Google Calendar
        add_event_url = f'{BACKEND_URL}:5000/add_event'
        response = requests.post(add_event_url, json=event_data)

        if response.status_code == 200:
            await interaction.response.send_message(f"Event '{summary}' added successfully!")
        else:
            await interaction.response.send_message(f"Failed to add event. Error: {response.status_code}")
    
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}")

@tree.command(name='choose', description='Choose randomly between given options')
async def choose(interaction: discord.Interaction, options: str):
    # Split the options by commas
    options_list = [option.strip() for option in options.split(',')]

    if not options_list or len(options_list) < 2:
        await interaction.response.send_message("You need to provide at least one option.")
        return

    choice = random.choice(options_list)
    responses = [
        f"Asking for help? I guess we'll do {choice}",
        f"You can never make decisions can you? {choice} it is",
        f"Another choice? Then, {choice}",
        f"I suppose we'll go with {choice}"
    ]
    
    response_message = random.choice(responses)  # Pick a random response template
    
    await interaction.response.send_message(response_message)

# Get the context limit of KoboldCPP
def get_context_limit() -> int:
    """Fetch current max context length from KoboldCPP (fallback to default)."""
    try:
        resp = requests.get("http://192.168.1.183:5001/api/v1/config/max_context_length", timeout=5)
        if resp.status_code == 200:
            print(f"[Bot] Using context limit: {CHAT_CONTEXT_LIMIT}")
            return int(resp.json().get("value", DEFAULT_CONTEXT_LIMIT))
    except Exception as e:
        print(f"[KoboldCPP] Failed to get context length: {e}")
    return DEFAULT_CONTEXT_LIMIT

CHAT_CONTEXT_LIMIT = DEFAULT_CONTEXT_LIMIT

def generate_reply(prompt, websearch_text=None) -> str:
    """Send prompt to KoboldCPP and get a reply."""
    try:
        payload = build_payload(prompt, websearch_text=websearch_text)
        response = requests.post(url, json=payload,timeout=60)
        data = response.json()
        return data.get("results", [{}])[0].get("text", "").strip()
    except Exception as e:
        print(f"[Error contacting KoboldCPP] {e}")
        return "(Error: LLM not responding)"
    
@tree.command(name='setchat', description='Set the channel for chatting with the bot')
async def setchat(interaction: discord.Interaction):
    global CHAT_CHANNEL_ID
    CHAT_CHANNEL_ID = interaction.channel_id
    await interaction.response.send_message(f"This channel ({interaction.channel.name}) is now the chat channel.")

@tree.command(name="context_size", description="Show current chat context size")
async def context_size(interaction: discord.Interaction):
    CHAT_CONTEXT_LIMIT = get_context_limit()
    total_chars = sum(len(msg) for _, msg in chat_memory)
    approx_tokens = total_chars // 3
    await interaction.response.send_message(
        f"Current context size: {total_chars} characters (~{approx_tokens} tokens). Max context {CHAT_CONTEXT_LIMIT}"
    )

@tree.command(name="clear_chat", description="Clear the current chat history and memory")
async def clear_chat(interaction: discord.Interaction):
    # global chat_memory
    chat_memory.clear()
    save_chat_history()
    await interaction.response.send_message("Chat memory cleared.")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    msg = reaction.message
    if msg.id not in bot_responses:
        return

    record = bot_responses[msg.id]
    current_index = record["index"]

    # ➡️ → generate a new variant
    if str(reaction.emoji) == "➡️":
        # Make a clean copy of chat memory, excluding last assistant message
        trimmed_memory = chat_memory.copy()
        if trimmed_memory and trimmed_memory[-1][0] == "assistant":
            trimmed_memory.pop()

        # Just send trimmed memory to generate_reply
        new_reply = generate_reply(trimmed_memory, websearch_text=None)
        trimmed_reply = trim_to_last_sentence(new_reply)
        # Save new variant
        record["alternatives"].append(trimmed_reply)
        record["index"] = len(record["alternatives"]) - 1

        # Update Discord message and memory
        await msg.edit(content=trimmed_reply)
        for i in range(len(chat_memory) - 1, -1, -1):
            if chat_memory[i][0] == "assistant":
                chat_memory[i] = ("assistant", trimmed_reply)
                break
        save_chat_history()
        vc = msg.guild.voice_client
        if vc and vc.is_connected():
            # Generate TTS for the reply
            tts_result = tts_api.generate_tts(
                text=trimmed_reply,
                character_voice="ash_island.wav",  # pick your desired voice
                language="en",
                output_file_name="discord_reply"
            )
            # Play TTS in VC
            if tts_result:
                await play_tts_in_vc(vc, tts_result)
            else:
                print("Failed to generate TTS")


    # ⬅️ → revert to previous variant
    elif str(reaction.emoji) == "⬅️" and current_index > 0:
        record["index"] -= 1
        prev_reply = record["alternatives"][record["index"]]

        await msg.edit(content=prev_reply)
        for i in range(len(chat_memory) - 1, -1, -1):
            if chat_memory[i][0] == "assistant":
                chat_memory[i] = ("assistant", prev_reply)
                break
        save_chat_history()

    # Clean up user reaction so they can click again
    try:
        await msg.remove_reaction(reaction.emoji, user)
    except Exception:
        pass

@bot.event
async def on_message_edit(before, after):
    # Only respond if the edit is in the chat channel and not from the bot
    if CHAT_CHANNEL_ID != 0 and after.channel.id == CHAT_CHANNEL_ID:
        if after.author == bot.user:
            return

        # Update the last user message in chat_memory
        # (Assumes last entry is the user's message)
        for i in range(len(chat_memory) - 1, -1, -1):
            if chat_memory[i][0] == "user":
                chat_memory[i] = ("user", after.content)
                break
        save_chat_history()

        # Regenerate the assistant's reply
        async with after.channel.typing():
            reply = generate_reply(chat_memory)
            trimmed_reply = trim_to_last_sentence(reply)

        # Update last assistant message in chat_memory
        for i in range(len(chat_memory) - 1, -1, -1):
            if chat_memory[i][0] == "assistant":
                chat_memory[i] = ("assistant", trimmed_reply)
                break
        save_chat_history()

        # Edit the last bot message in Discord
        if last_bot_msg_id:
            try:
                bot_msg = await after.channel.fetch_message(last_bot_msg_id)
                await bot_msg.edit(content=trimmed_reply)
            except Exception as e:
                print(f"Failed to edit bot message: {e}")
        print(f"Message edited from: {before.content} to: {after.content}")

@bot.event
async def on_message_delete(message):
    # Ignore non-user messages or embeds
    if message.embeds:
        return

    # Try to find and remove the deleted message from chat history
    global chat_memory
    # Clean transcription username prefix just like in on_message
    content = message.content.replace("**mizuki_sakai**:", "").strip()
    # Remove first match of this message text from chat history
    for i, (_, msg) in enumerate(chat_memory):
        if msg == content:
            del chat_memory[i]
            print(f"Deleted from chat history: {content}")
            break

    # Also remove from persistent storage, if you’re saving history
    save_chat_history()
 
####### voice 
# join voice
@tree.command(name="join", description="Join the voice channel you're in.")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if vc:
        await vc.move_to(channel)
        await interaction.response.send_message(f"Moved to {channel}.")
    else:
        await channel.connect()
        await interaction.response.send_message(f"Joined {channel}.")
    if tts_api.initialize():
        print("AllTalk API initialized successfully.")
        # Display all server information
        tts_api.display_server_info()
        # Enable DeepSpeed for optimized performance
        if tts_api.set_deepspeed(True):
            print("DeepSpeed enabled.")
        else:
            print("Failed to enable DeepSpeed.")

@tree.command(name="leave", description="Disconnect from the current voice channel.")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client

    if vc and vc.is_connected():
        await vc.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel.")
    else:
        await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)


@bot.event
async def on_voice_state_update(member, before, after):
    # Ignore bots moving around
    if member.bot:
        return

    # If someone left a voice channel
    if before.channel is not None:
        voice_channel = before.channel

        # Find if our bot is connected to the same channel
        for vc in bot.voice_clients:
            if vc.channel == voice_channel:
                # Check for remaining non-bot users
                non_bots = [m for m in voice_channel.members if not m.bot]
                if not non_bots:
                    await vc.disconnect()
                    print(f"Auto-disconnected from {voice_channel} (empty).")

# get tts file duration
def get_wav_duration(filename):
        with wave.open(filename, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)
        
async def play_tts_in_vc(vc: discord.VoiceClient, tts_result):
    """
    Downloads the TTS audio from AllTalk and plays it in the connected voice channel.
    """
    if tts_result:
        print(f"\nTTS generated: {tts_result['output_file_url']}")
    if not tts_result or 'output_file_url' not in tts_result:
        print("No TTS audio URL available")
        return

    # Prepend base URL
    url = f"{tts_api.base_url}{tts_result['output_file_url']}"
    # Download audio to a temporary file
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print("Failed to download TTS audio")
                return
            data = await resp.read()
            with open("temp_tts.wav", "wb") as f:
                f.write(data)
    
    duration = get_wav_duration("temp_tts.wav")
    print(f"TTS duration: {duration:.2f}s")

    # Play in VC
    if vc.is_playing():
        vc.stop()
    # send event to VRM client 
    #await send_tts_text({"event": "speak", "text": text_str, "duration": duration})
    await send_audio()
    vc.play(discord.FFmpegPCMAudio(executable="C:/ffmpeg/bin/ffmpeg.exe",source="temp_tts.wav"))

async def send_audio():
    """
    Reads the TTS audio file and sends it to all connected WebSocket clients.
    """
    if not connected_clients:
        print("No browser clients connected; skipping broadcast.")
        return

    try:
        with open("temp_tts.wav", "rb") as f:
            audio_data = f.read()
        
        # Send the audio data to all connected clients concurrently
        tasks = [client.send(audio_data) for client in connected_clients]
        await asyncio.gather(*tasks)
        print(f"Successfully sent audio data to {len(connected_clients)} client(s).")

    except FileNotFoundError:
        print("Error: temp_tts.wav not found for broadcasting.")
    except Exception as e:
        print(f"An error occurred during audio broadcast: {e}")

async def tts_stream(websocket):
    """
    Handles new WebSocket connections, keeps them alive, and removes them on disconnect.
    This function's job is to simply manage the connection lifecycle.
    """
    print("Browser connected.")
    connected_clients.add(websocket)
    try:
        # This line is crucial: it keeps the connection open indefinitely
        # until the client closes it.
        await websocket.wait_closed()
    finally:
        print("Browser disconnected.")
        connected_clients.remove(websocket)

async def main():
    load_dotenv()
    # Gemini setup for image captioning
    # Configure Gemini API (replace with your actual API key)
    api_key = os.getenv('GOOGLE_API_KEY')
    genai.configure()

    TOKEN = os.getenv('TOKEN')
    try:
        async with websockets.serve(tts_stream, "0.0.0.0", 8765):
            print("webserver running")
            await bot.start(TOKEN)
        
    finally:
        await bot.close()
    # Run the bot
    # bot.run(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
