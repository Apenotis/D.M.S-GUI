@echo off
setlocal

REM Build D.M.S GUI as a one-folder Windows app.
REM Prefer the workspace venv and fall back to the launcher on PATH.
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

cd /d "%~dp0"

"%PYTHON_EXE%" build_exe.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

endlocal
