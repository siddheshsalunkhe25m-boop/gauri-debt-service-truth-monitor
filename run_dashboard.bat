@echo off
cd /d "%~dp0"
echo Starting the Debt-Service Truth Monitor dashboard...
py -m streamlit run dashboard\app.py
if errorlevel 1 python -m streamlit run dashboard\app.py
pause
