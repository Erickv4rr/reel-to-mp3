@echo off
rem Starts the Reel to MP3 web server in the background and opens it in the browser.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0server.py"
timeout /t 2 /nobreak >nul
start "" http://localhost:8765
