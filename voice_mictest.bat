@echo off
rem Mic test: level, playback, what Whisper heard. Options: --list, --device N, --record NAME
cd /d "%~dp0"
call pyenv.bat
"%PY%" -m tomits.voice_mictest %*
pause
