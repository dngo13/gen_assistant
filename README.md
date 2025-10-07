# Google Calendar Reminders with LLM
## Requirements
- Python 
- flask
- google calendar api
- koboldcpp
- apscheduler
- discord api

`pip install Flask google-api-python-client google-auth-httplib2 google-auth-oauthlib` \
`pip install apscheduler` \
`pip install discord discord-webhook `
`pip install python-dotenv`
### Commands
Create a virtual environment if you don't have it, ensure you are in the current working directory. 
`python3 -m venv api_env`

Run 'start.bat' to start the scripts and virtual environment.
(OLD) Start the virtual environment in command prompt by `.\api_env\Scripts\activate` then run `python backend.py` to start the flask server. Run `bot_run.py` to start the discord bot. 

`http://your-ip-address:5000/` to check if running.
`http://your-ip-address:5000/get_upcoming_events` to check calendar events in json

