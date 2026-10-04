@echo off
chcp 65001 >nul
if not exist venv ( python -m venv venv )
call venv\Scripts\activate
pip install -r requirements.txt
if not exist instance\hr_system.db ( python seed.py )
echo.
echo افتح المتصفح على: http://127.0.0.1:8000
python app.py
