import discord
from discord.ext import commands
from discord import app_commands
import requests
import asyncio
import datetime
import discord_webhook
from dotenv import load_dotenv
import os
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


# Slash command to manually pull Google Calendar events and send them to the Discord channel
@bot.command(name='get_events')
# @tree.command(name="get_events", description="List upcoming Google Calendar events")
async def get_events(message):
    try:
        # Pull events from the Flask backend
        events_url = 'http://localhost:5000/get_upcoming_events'
        response = requests.get(events_url)

        if response.status_code == 200:
            events = response.json().get('events', [])
            if events:
                # Format the events for better readability
                event_messages = []
                for event in events:
                    summary = event.get('summary', 'No Title')
                    start_time = event.get('start_time', 'No Time')
                    description = event.get('description', 'No description provided')
                    event_messages.append(f"**Event:** {summary}\n**Start Time:** {start_time}\n**Description:** {description}")

                # Send each event as a message
                for event_message in event_messages:
                    await message.channel.send(event_message)
            else:
                await message.channel.send("No upcoming events.")
        else:
            await message.channel.send("Failed to get events.")

    except Exception as e:
        await message.channel.send("An error occurred")

# Function to send a reminder directly to Discord (called from the backend)
@bot.event
async def send_reminder_to_discord(reminder):
    # Ensure the bot's cache is ready
    # await bot.wait_until_ready()
    discord_webhook_url = 'https://discord.com/api/webhooks/1284279940858249256/v3TzTaTGNMm7aiRhlUuqeCx0L6FnJsa1_CyBGo2VZTmdeHhmFbJMV6f08v2gtlhY6xHq'
    webhook = discord_webhook.DiscordWebhook(url=discord_webhook_url)
    webhook.content = reminder
    response = webhook.execute()
    

@bot.event
async def on_message(message):
    # Get the message content, make it lowercase
    msg_content: str = message.content.lower()
    if msg_content.startswith(command_prefix):
        msg_content = msg_content.replace(command_prefix,"")
        if message.author == bot.user:
            return
        match msg_content: 
            case "hello":
                await message.channel.send(f'Hello, {message.author.mention}!')
            case "help":
                await message.channel.send('No, there is no help available.')
            case "ping":
                await message.channel.send(f'Pong! {round(bot.latency * 1000)}ms')
            case "get_events":
                await message.channel.send('Getting events, please hold.')
                await get_events(message)

def main():
    load_dotenv()
    TOKEN = os.getenv('TOKEN')

    # Run the bot
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
