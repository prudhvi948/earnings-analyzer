@echo off
REM Create a virtual environment in .venv, install requirements, and run the app
if not exist ".venv" (
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
    echo Using existing .venv
)

.venv\Scripts\python.exe earnings_app.py
