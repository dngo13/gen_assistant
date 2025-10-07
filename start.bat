@echo off
cd C:\Users\diane\Documents\AI-Files\gen_assistant
call api_env\Scripts\activate
start python backend.py

start python bot_run.py
pause