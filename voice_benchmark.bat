@echo off
rem Compares Whisper model sizes on your clips in tests\audio.
cd /d "%~dp0"
call pyenv.bat
"%PY%" -m tomits.voice_benchmark %*
pause
