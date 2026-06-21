@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\update_tool.ps1" %*
pause
