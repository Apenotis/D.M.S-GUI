@echo off
setlocal

REM Build D.M.S GUI as a one-folder Windows app (recommended for external data files)
set "PYTHON_EXE=e:\Doom Classic\Test\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Python executable not found: %PYTHON_EXE%
  exit /b 1
)

cd /d "%~dp0"

"%PYTHON_EXE%" build_exe.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

endlocal
