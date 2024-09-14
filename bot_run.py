import discord
from discord.ext import commands
from discord import app_commands
import requests
import asyncio
import time
import discord_webhook

intents = discord.Intents.default()
intents.message_content = True

# Use commands.Bot to handle slash commands
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree
# Replace with your actual bot token
TOKEN = "MTI4NDMxNDYyODY1NDEwODczMw.GbthvJ.mKjTXSoUa3Ql5crV8Y2eC93bYa_oXI98P-bRSw"

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await bot.get_channel(1191949009405878314).send("Sirius is online")
    await tree.sync()
    # await bot.wait_until_ready()  # Wait until the bot is fully initialized


# Slash command to manually pull Google Calendar events and send them to the Discord channel
# @bot.command(name='get_events')
@tree.command(name="get_events", description="List upcoming Google Calendar events")
async def get_events(interaction: discord.Interaction):
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
                    event_messages.append(f"**Event:** {summary}\n**Start Time:** {start_time}")

                # Send each event as a message
                for event_message in event_messages:
                    await interaction.response.send_message(event_message, ephemeral=True)  # Send event message privately
            else:
                await interaction.response.send_message("No upcoming events.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Failed to get events. Error code: {response.status_code}", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

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
    # if message.author == bot.user:
    #     return
    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')
    if message.content.startswith('!help'):
        await message.channel.send('No, there is no help available.')

def main():
    # Run the bot
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
