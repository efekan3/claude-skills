@echo off
rem Installeer Memory Hub: skill, hooks, MCP, snelkoppeling, autostart en eerste import
cd /d "%~dp0"
where py >nul 2>nul && (py -3 memory_hub.py install) || (python memory_hub.py install)
pause
