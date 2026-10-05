@echo off
rem The daily snapshot (RUNBOOK section 8): %1 = data home, %2 = log file.
set PYTHONUTF8=1
set PEGASUS_DATA_HOME=%~1
echo ==== %DATE% %TIME% >> "%~2"
"C:\Users\Galaxy\miniconda3\envs\pegasus\Scripts\pegasus-data.exe" snapshot --json >> "%~2" 2>&1
echo exit=%ERRORLEVEL% >> "%~2"
