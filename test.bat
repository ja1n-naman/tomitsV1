@echo off
cd /d "%~dp0"
call pyenv.bat
"%PY%" -c "import pytest, rich, sqlalchemy, plyer, schedule, flask, numpy" 2>nul || "%PY%" -m pip install -r requirements.txt
"%PY%" -m pytest -q %*
