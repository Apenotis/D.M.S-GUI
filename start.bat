@echo off
setlocal
cd /d "%~dp0"

REM If release.ps1 is blocked by ExecutionPolicy, run:
REM powershell -NoProfile -ExecutionPolicy Bypass -File .\release.ps1 -NewVersion <version>

set "PYTHONPATH=%CD%"
set "PYTHON_EXE=%CD%\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=pythonw"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" recovery_launcher.py
endlocal
exit /b %errorlevel%