@echo off
rem Start Memory Hub (Windows). Eerste keer: dubbelklik install-memory-hub.bat
cd /d "%~dp0"
where py >nul 2>nul && (start "" pyw -3 memory_hub.py open) || (start "" pythonw memory_hub.py open)
