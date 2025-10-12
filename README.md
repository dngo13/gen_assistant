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


------------
# WIP VRM Loader using Three.JS
- Install NodeJS (https://nodejs.org/en/download)
- Install three.js (https://threejs.org/manual/#en/installation) and a build tool, the three.js guide uses Vite
- Then install pixiv's vrm in the project folder `model_loader/` and run `npm install three @pixiv/three-vrm`
