@echo off
setlocal

set MODE=%1
if "%MODE%"=="" set MODE=minimal

python "%~dp0make_test_snapshot.py" --mode %MODE%

endlocal
