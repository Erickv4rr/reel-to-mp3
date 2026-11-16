@echo off
rem Starts Reel to MP3 from the source code (the installed app does the same thing).
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
