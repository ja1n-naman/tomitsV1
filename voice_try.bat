@echo off
rem Runs a .wav (or --text "...") through the voice pipeline without executing anything.
cd /d "%~dp0"
call pyenv.bat
"%PY%" -m tomits.voice_try %*
pause
