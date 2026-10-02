@echo off
rem Picks the Python to use: the private .venv made by start-tomits.bat, else the one on PATH.
if exist "%~dp0.venv\Scripts\python.exe" (set "PY=%~dp0.venv\Scripts\python.exe") else (set "PY=python")
