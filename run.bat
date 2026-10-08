@echo off
rem Terminal version of tomits (uses the same database as the web app). Installs dependencies the first time.
cd /d "%~dp0"
call pyenv.bat
"%PY%" -c "import rich, sqlalchemy, plyer, schedule" 2>nul || "%PY%" -m pip install -r requirements-core.txt
"%PY%" -m tomits %*
