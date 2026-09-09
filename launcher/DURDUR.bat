@echo off
rem ============================================================
rem  tactic11 - calisan siteyi ve API'yi durdurur.
rem  Sunucular pencereden bagimsiz/gizli calisiyor; bu, terminali kapatinca
rem  sitenin kapanmamasi icin bilincli bir tercih. Durdurmanin yolu burasi.
rem
rem  Yalniz KOMUT SATIRI bu projeyi gosteren surecler kapatilir; makinedeki
rem  baska node/python islerine dokunulmaz.
rem ============================================================
title tactic11 - durdur
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sunucu-durdur.ps1" -Bilesen hepsi
echo.
echo Tekrar acmak icin BASLAT.bat'a cift tikla.
echo.
pause
