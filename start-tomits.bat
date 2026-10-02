@echo off
rem ===================================================================
rem  tomits - double-click to start. Windows only for now.
rem  First run: makes a private Python environment (.venv) and installs
rem  what tomits needs, after asking. Then starts tomits and opens your
rem  browser at http://127.0.0.1:3000 (or the next free port).
rem  Everything stays on this computer.
rem ===================================================================
setlocal
cd /d "%~dp0"
title tomits

where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto oldpython

if exist ".venv\Scripts\python.exe" goto check
echo.
echo  Welcome to tomits.
echo.
echo  This first start sets up a private Python folder (.venv) inside the
echo  tomits folder and downloads the packages tomits needs: about 10 MB.
echo  Nothing else on your computer is changed.
echo.
choice /c YN /m " Download and install them now"
if errorlevel 2 goto declined
echo.
echo  Creating .venv ...
python -m venv .venv
if errorlevel 1 goto venvfail
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-core.txt
if errorlevel 1 goto pipfail
echo  Done.
echo.
echo  Optional: voice control. Speech packages are about 130 MB, and the
echo  speech model is downloaded later by voice_setup.bat, which asks first.
echo  You can skip this: typing in the box at the top does everything too.
echo.
choice /c YN /m " Install the voice packages now"
if errorlevel 2 goto novoice
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-voice.txt
if errorlevel 1 echo  The voice packages didn't install. Typing still works; try voice_setup.bat later.
goto check
:novoice
echo  Skipped. Run voice_setup.bat any time to add voice.

:check
".venv\Scripts\python.exe" -c "import flask, sqlalchemy, rich, schedule" >nul 2>nul
if errorlevel 1 goto repair
goto start

:repair
echo.
echo  Some packages are missing or damaged. Reinstalling them (about 10 MB) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-core.txt
if errorlevel 1 goto pipfail

:start
echo.
echo  Starting tomits ...
".venv\Scripts\python.exe" -u -m tomits.web %*
if errorlevel 1 goto serverfail
goto end

:nopython
echo.
echo  tomits needs Python, and it isn't installed (or isn't on PATH).
echo.
echo  What to do:
echo    1. Go to https://www.python.org/downloads/ and download Python 3.12 or newer.
echo    2. Run the installer and TICK "Add python.exe to PATH" on the first screen.
echo    3. Double-click start-tomits.bat again.
goto fail

:oldpython
echo.
echo  Your Python is too old for tomits; it needs 3.10 or newer.
echo  Install a newer one from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),
echo  then double-click start-tomits.bat again.
goto fail

:declined
echo.
echo  Nothing was downloaded or changed. Double-click start-tomits.bat when you're ready.
goto fail

:venvfail
echo.
echo  Couldn't create the private Python folder (.venv).
echo  Check this folder isn't read-only and the disk has space, then try again.
echo  If it keeps failing, delete the .venv folder inside the tomits folder and start again.
goto fail

:pipfail
echo.
echo  Installing packages failed (see the message above).
echo  Usually this means no internet connection right now, or a firewall blocking pip.
echo  Connect to the internet and double-click start-tomits.bat again.
echo  Your tasks and goals are safe; nothing was deleted.
goto fail

:serverfail
echo.
echo  tomits stopped with an error (see the message above).
echo  Your data is safe: every change was saved as you made it.
echo  If the message mentions a backup, free some disk space and try again.
goto fail

:fail
echo.
pause
exit /b 1

:end
endlocal
