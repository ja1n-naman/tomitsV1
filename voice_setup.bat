@echo off
rem Adds voice: installs the speech packages (about 130 MB) and downloads the models. Asks before each download.
rem No account; no audio or text leaves this PC.
cd /d "%~dp0"
call pyenv.bat
"%PY%" -c "import faster_whisper, sounddevice, pyttsx3, numpy" 2>nul && goto models
echo The voice packages aren't installed yet (about 130 MB download).
choice /c YN /m "Install them now"
if errorlevel 2 goto end
"%PY%" -m pip install -r requirements-voice.txt
if errorlevel 1 goto end
:models
"%PY%" -m tomits.voice_setup %*
:end
pause
