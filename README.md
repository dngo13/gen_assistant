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

### Commands
Start the virtual environment in command prompt by `/api_env/Scripts/activate`
Then run `python backend.py` to start the flask server. 

`http://localhost:5000/` to check if running.
`http://localhost:5000/get_upcoming_events` to check calendar events in json

Run `bot_run.py` to start the discord bot. 