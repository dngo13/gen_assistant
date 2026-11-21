@echo off
cd C:\Users\diane\Nextcloud\Documents\AI-Files\gen_assistant
call api_env\Scripts\activate
start python backend_run.py

start python bot_run.py

start "CODE27 calendar tool" cmd /k "cd /d C:\Users\diane\Nextcloud\Documents\AI-Files\gen_assistant && python CODE27\integrations\calendar_tool.py http://10.0.0.101:8081 --backend http://127.0.0.1:5000"

REM cd C:\Users\diane\Nextcloud\Documents\AI-Files\gen_assistant\model_loader
REM npx vite --host
pause