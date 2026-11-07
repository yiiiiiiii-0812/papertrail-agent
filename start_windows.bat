@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if not exist .venv\Scripts\python.exe (
  echo Creating a local Python environment...
  py -m venv .venv
  if errorlevel 1 (
    echo Python was not found. Install Python 3.11+ from python.org.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies. Check your Internet connection.
  pause
  exit /b 1
)
echo.
echo PaperTrail is starting.
echo Open http://127.0.0.1:8000 in your browser.
echo To enable GPT-4.1, edit OPENAI_API_KEY in the .env file, then restart.
echo.
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
