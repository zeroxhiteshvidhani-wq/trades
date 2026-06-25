@echo off
:: Apne project folder mein ensure karein
cd /d "%~dp0"

:: Virtual environment ka use karke streamlit run karein
call .venv\Scripts\python.exe -m streamlit run main.py
pause