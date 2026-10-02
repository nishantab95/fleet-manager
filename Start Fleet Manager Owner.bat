@echo off
setlocal
title Fleet Manager Owner
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-owner-web.ps1"
endlocal
