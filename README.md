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
Voice replies default to off and require the bot to be connected with `/join`.
The backend, voice, and Home Assistant action commands are administrator-only.
The selection and voice setting are saved in the ignored
`bot_config/discord_settings.json`.

The CODE27 calendar integration also registers `get_current_weather`, which
reads the `weather.forecast_home` entity through Home Assistant's REST API.
Set `HA_BASE_URL` and a Home Assistant long-lived access token in `.env`, then
run this from the repository root and keep it running:

`python CODE27/integrations/calendar_tool.py http://CODE27_DEVICE_IP:8081 --backend http://127.0.0.1:5000`

After registering the tools, start a new CODE27 conversation on the device so
the tools are available. Discord chat uses that CODE27 conversation, and sends
the resulting assistant response—including calendar or weather tool results—to
the configured Discord chat channel.

CODE27 Discord replies have 🔄 and 🗑️ reactions. 🔄 removes that turn's saved
user/assistant records from the device and regenerates the reply from the
remaining history. 🗑️ removes the reply and that turn's records; the original
Discord prompt remains. Deleting the original Discord prompt also removes its
mapped CODE27 turn and reply. These controls are available only while the bot
process retains the message-to-turn mapping.

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
