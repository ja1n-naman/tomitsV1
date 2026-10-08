@echo off
rem (kept for v1.5 users) Same as voice_mictest.bat
cd /d "%~dp0"
call pyenv.bat
"%PY%" -m tomits.voice_mictest %*
pause
