@echo off
REM Run this on Windows with Python 3.11+ installed.
cd /d %~dp0\..
py -3 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
pyinstaller --noconfirm --windowed --name AtlasTrader --collect-all pyqtgraph --collect-all ccxt --paths src launcher.py
if errorlevel 1 exit /b 1
echo App created in dist\AtlasTrader\
