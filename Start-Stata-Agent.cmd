@echo off
start "" /b powershell.exe -NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0start-stata-agent.ps1"
