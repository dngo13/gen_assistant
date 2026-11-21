# Personal AI Assistant
This is a personal AI assistant connected to Home Assistant for automations, Google calendar reminders, prescription reminders, and gas reminders.
It also connects to discord for reminder pings, as well as chat and voice capability. This connects to KoboldCPP for LLM and AllTalk TTS for voice.

## Requirements
- Python 
- Flask
- Google calendar api
- Koboldcpp
- apscheduler
- Discord api
- PyNaCl

As of 10/11/25 just run `pip install -r requirements.txt`. 

`pip install Flask google-api-python-client google-auth-httplib2 google-auth-oauthlib` \
`pip install apscheduler` \
`pip install discord discord-webhook `
`pip install python-dotenv`
`pip install PyNaCl`
`pip install pytz`
### Commands
Create a virtual environment if you don't have it, ensure you are in the current working directory. 
`python3 -m venv api_env`

Run `start.bat` to start the scripts and virtual environment.
(OLD) Start the virtual environment in command prompt by `.\api_env\Scripts\activate` then run `python backend.py` to start the flask server. Run `bot_run.py` to start the discord bot. 

`http://your-ip-address:5000/` to check if running. This will also display all the routes.
`http://your-ip-address:5000/get_upcoming_events` to check calendar events in json

## Discord, CODE27, and Home Assistant

If you do not already have `.env`, copy `.env.example` to `.env`; otherwise add
the needed settings without replacing existing secrets. Set `TOKEN`,
`CODE27_DEVICE_URL`, and `CODE27_CREDENTIALS_PATH`. The default Discord backend is CODE27; it uses the
device's active conversation and device-side history. Pair the device once using
the CODE27 calendar integration below. Choose another backend any time with
`/llm_backend` (`CODE27` or `KoboldCpp`). KoboldCpp retains its existing local
history in `bot_config/chat_history.json`.

Use `/voice enabled:true` or `/voice enabled:false` to control spoken replies.
Voice replies default to off. When enabled, CODE27 speaks each reply on the
device; the bot also plays it in Discord only while connected to a voice channel
with `/join`. The backend, voice, and Home Assistant action commands are administrator-only.
The selection and voice setting are saved in the ignored
`bot_config/discord_settings.json`.

The CODE27 integration registers calendar lookup, current weather, web search,
and persistent user-note tools. Set `HA_BASE_URL` and a Home Assistant
long-lived access token in `.env` for weather. Web search uses a local SearXNG
instance, with `SEARXNG_URL` defaulting to `http://127.0.0.1:8080`. SearXNG is
free and does not require an API key, but you need to run an instance yourself
(for example, with Docker or Podman) and enable the JSON search format. See the
[SearXNG installation guide](https://docs.searxng.org/admin/installation-docker.html)
and [search API docs](https://docs.searxng.org/dev/search_api.html). Run the
CODE27 tool integration from the repository root and keep it running:

`python CODE27/integrations/calendar_tool.py http://CODE27_DEVICE_IP:8081 --backend http://127.0.0.1:5000`

After registering the tools, start a new CODE27 conversation on the device so
the updated tool list is available. The existing configured chat channel and
character channels send the resulting assistant response, including tool
results, to Discord. Web search returns source links; SearXNG must be reachable
from the machine running this integration. The existing KoboldCpp search path
uses the same `SEARXNG_URL`.

The `search_user_notes`, `remember_user_note`, and `forget_user_note` tools
provide notes shared across all CODE27 characters. The assistant should save a
note only when you explicitly ask it to remember something. Saving and deleting
notes require confirmation on the device. Notes are stored locally in the
ignored file `bot_config/user_notes.json`; do not ask it to save passwords,
tokens, or other credentials.

Calendar and reminder features already exist: CODE27 can read events for today,
tomorrow, or the next seven days; Discord also has `/get_events` and `/add_event`.
The Flask backend scans for upcoming events every 30 minutes and schedules
15-minute-before reminders; it also schedules the existing daily prescription
reminder. Reminders go to Discord and, when CODE27 is available, are spoken on
the device. Conversational editing or cancellation of calendar events is not
currently available.

To give Sirius and Minami separate Discord channels and CODE27 histories, create
a Discord webhook in each character's channel. Put each webhook URL in the
matching `DISCORD_CHARACTER_WEBHOOK_<NAME>_URL` variable in your local `.env`.
Set each webhook's avatar in Discord; the bot uses that configured avatar.
Do not commit `.env` or share webhook URLs.

In the Sirius channel, run `/character` with `name:Sirius` or send `!character
Sirius`; in the Minami channel, use `name:Minami` or `!character Minami` (use
the exact names shown on CODE27). The bot verifies each character and its
channel webhook, then saves the
channel-to-slot mapping in `bot_config/discord_settings.json`. Messages in a
mapped channel switch CODE27 to that character's slot before sending the turn,
so each slot keeps its own CODE27 history. This API requires CODE27 1.6.0.
Character channels use CODE27 even if the global `/llm_backend` setting is
KoboldCpp; that setting continues to apply to the existing chat channel.

Only the latest bot reply keeps its reaction controls. CODE27 Discord replies
have 🔄 and 🗑️ reactions. 🔄 removes that turn's saved
user/assistant records from the device and regenerates the reply from the
remaining history. 🗑️ removes the reply and that turn's records; the original
Discord prompt remains. Deleting the original Discord prompt also removes its
mapped CODE27 turn and reply. These controls are available only while the bot
process retains the message-to-turn mapping.

The Flask backend scans Google Calendar for upcoming events when it starts and
every 30 minutes afterward, scheduling reminders for 15 minutes before each
event. If a scan finds an event whose 15-minute reminder time has passed but
which has not started yet, it sends that reminder immediately. These scheduled
reminders ask CODE27 to generate the
reminder, speak it aloud on the CODE27 device, and post the same text to Discord.
They use no chat-history retention and no tools, and won't interrupt an active
CODE27 conversation. Keep the Flask backend running; the device must be
reachable and available for voice playback. If CODE27 is unavailable or busy,
the backend logs the error and still posts a plain-text fallback reminder to
Discord (it cannot speak that fallback on the device).

The `/ha_action` command can trigger `fuel_reminder`, `weather_reminder`,
`daily_reminder`, `log_gas_entry`, or `get_gas_log` through Home Assistant's REST
API. It confirms the service call in Discord; the Home Assistant REST command's
own response is not relayed by this trigger.

------------
# WIP VRM Loader using Three.JS
- Install NodeJS (https://nodejs.org/en/download)
- Install three.js (https://threejs.org/manual/#en/installation) and a build tool, the three.js guide uses Vite
- Then install pixiv's vrm in the project folder `model_loader/` and run `npm install three @pixiv/three-vrm`
- Run `npm run build` to build
- Use `npx vite --host` to run
