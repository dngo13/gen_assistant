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
intents = discord.Intents.default()
intents.message_content = True

# Set command prefix
command_prefix='!'
bot = commands.Bot(command_prefix, intents=intents)
tree = bot.tree

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
        events_url = 'http://100.70.126.54:5000/get_upcoming_events'
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
    discord_webhook_url = 'https://discord.com/api/webhooks/1284279940858249256/v3TzTaTGNMm7aiRhlUuqeCx0L6FnJsa1_CyBGo2VZTmdeHhmFbJMV6f08v2gtlhY6xHq'
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
    response = requests.post('http://100.70.126.54:5000/add_prescription', json={'prescription': prescription})
    if response.status_code == 200:
        await interaction.response.send_message(f"Prescription '{prescription}' added.")
    else:
        await interaction.response.send_message(f"Error: {response.json().get('error')}")

@tree.command(name='remove_prescription', description='Remove a prescription')
@app_commands.describe(prescription="Prescription name and dose")
async def remove_prescription(interaction: discord.Interaction, prescription: str):
    print("Removing prescription.")
    response = requests.post('http://100.70.126.54:5000/remove_prescription', json={'prescription': prescription})
    if response.status_code == 200:
        await interaction.response.send_message(f"Prescription '{prescription}' removed.")
    else:
        await interaction.response.send_message(f"Error: {response.json().get('error')}")

@tree.command(name='get_prescriptions', description='List all prescriptions')
async def get_prescriptions(interaction: discord.Interaction):
    print("Getting prescriptions.")
    response = requests.get('http://100.70.126.54:5000/get_prescriptions')
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
    response = requests.get('http://100.70.126.54:5000/get_gas_log')
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

@bot.event
async def on_message(message):
    # Get the message content, make it lowercase
    msg_content: str = message.content.lower()
    if msg_content.startswith(command_prefix):
        msg_content = msg_content.replace(command_prefix,"")
        if message.author == bot.user:
            return
        match msg_content: 
            case "help":
                await message.channel.send('You need my help again? Tsk tsk. Here are the commands.\n ping, sync, get_events, add_event, get_prescriptions, add_prescription, remove_prescription')
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
        add_event_url = 'http://100.70.126.54:5000/add_event'
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

def main():
    load_dotenv()
    TOKEN = os.getenv('TOKEN')

    # Run the bot
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
