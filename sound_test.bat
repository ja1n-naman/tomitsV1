@echo off
rem Plays the tomits alarm tone 3 times and says whether it worked.
cd /d "%~dp0"
call pyenv.bat
"%PY%" -c "from tomits.ringer import WindowsTonePlayer as P; p=P(); [p.play_burst() for _ in range(3)]; print('Sound OK: you should have heard 3 short beep patterns.')" || echo Sound FAILED: see the error above.
pause
