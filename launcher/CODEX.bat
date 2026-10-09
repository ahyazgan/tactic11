@echo off
rem Manager'i diger projelerden ayri portlarda baslat.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-runtime.ps1" -OpenBrowser %*
if errorlevel 1 pause
