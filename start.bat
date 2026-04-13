@echo off
setlocal
cd /d "%~dp0"

set "PYTHONPATH=%CD%"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" recovery_launcher.py
endlocal
exit /b %errorlevel%