@echo off
cd C:\Users\diane\Nextcloud\Documents\AI-Files\gen_assistant
call api_env\Scripts\activate
start python backend_run.py

start python bot_run.py
pause