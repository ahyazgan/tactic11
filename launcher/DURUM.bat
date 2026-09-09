@echo off
rem tactic11 - ne calisiyor, guncel mi, otomatik acilis kurulu mu?
rem Sunucular gizli calistigi icin durumu gormenin baska yolu yok.
title tactic11 - durum
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0durum.ps1"
pause
