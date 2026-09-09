@echo off
rem ============================================================
rem  tactic11 - tek tikla baslatici. "npm run dev" de bunu acar.
rem  Siteyi hizli (production) modda hazirlar, tarayiciyi acar.
rem  Sunucu pencereden BAGIMSIZ ve gizli calisir: bu pencereyi
rem  veya terminali kapatmak siteyi kapatmaz.  Durdurmak: DURDUR.bat
rem
rem  BAYATLIK KORUMASI (2026-09-09): "zaten calisiyor" artik tek basina
rem  yeterli degil - calisan kopya ESKI KODU sunuyorsa yeniden derlenir.
rem ============================================================
title tactic11 - baslatici
rem Bu dosya launcher\ icinde; proje koku BIR UST klasordur (%~dp0..).
cd /d "%~dp0..\frontend"
set PS=powershell -NoProfile -ExecutionPolicy Bypass
set GUNCEL=%PS% -File "%~dp0guncel-mi.ps1"

rem 0) Kod, mevcut derlemeden yeni mi?  0=guncel  1=bayat/derleme yok
%GUNCEL% -Bilesen frontend >nul 2>&1
set FE=%errorlevel%

rem 1) 3000'de bizim HIZLI sunucu calisiyor VE guncel ise dokunma, tarayiciyi ac.
%PS% -Command "$c = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if (-not $c) { exit 1 }; $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); if ($p.CommandLine -like '*football-intelligence\frontend*' -and $p.CommandLine -notlike '*start-server.js*') { exit 0 }; exit 2"
set P3000=%errorlevel%
if "%P3000%"=="0" if "%FE%"=="0" (
  echo Site zaten calisiyor ve guncel - tarayici aciliyor.
  start "" "http://localhost:3000"
  ping -n 3 127.0.0.1 >nul
  goto end
)
if "%P3000%"=="0" (
  echo Site calisiyor ama ESKI KODU sunuyor - kod degismis.
  %GUNCEL% -Bilesen frontend
  echo Yeniden derlenip baslatilacak.
  echo.
)

rem 2) Eski/yavas kopyalari temizle.
echo Eski sunucular temizleniyor...
%PS% -File "%~dp0sunucu-durdur.ps1" -Bilesen frontend -Sessiz >nul 2>&1
ping -n 3 127.0.0.1 >nul

rem 2b) 3000'i hala proje-disi bir program tutuyorsa derleme yapma; adini soyle ve cik.
%PS% -Command "$c = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); Write-Host ('3000 portunu baska bir program tutuyor: ' + $p.Name + ' (PID ' + $c.OwningProcess + ')'); exit 2 }; exit 0"
if %errorlevel% neq 0 (
  echo O programi kapatip BASLAT'a tekrar cift tikla.
  pause
  goto end
)

rem 3) Derleme yok ya da kaynak degismis ise gorunur sekilde derle.
if not "%FE%"=="0" (
  echo Derleme aliniyor, birkac dakika surebilir...
  call npm run build
)
if not exist ".next\BUILD_ID" (
  echo.
  echo DERLEME HATASI - ustteki ciktiyi kontrol et.
  pause
  goto end
)

rem 4) Sunucuyu pencereden bagimsiz (gizli) baslat.
echo Sunucu baslatiliyor...
wscript "%~dp0baslat-gizli.vbs"

rem 5) Hazir olana kadar bekle (en cok ~60 sn).
set /a TRIES=0
:wait
%PS% -Command "if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { exit 0 }; exit 1"
if %errorlevel%==0 goto ready
set /a TRIES+=1
if %TRIES% geq 40 goto fail
ping -n 2 127.0.0.1 >nul
goto wait

:ready
echo.
echo Site hazir: http://localhost:3000   (eski adres :3001 de calisir)
%GUNCEL% -Bilesen frontend
echo Bu pencereyi KAPATABILIRSIN - site arka planda calismaya devam eder.
echo Durdurmak icin: DURDUR.bat
start "" "http://localhost:3000"
ping -n 5 127.0.0.1 >nul
goto end

:fail
echo.
echo Site acilamadi. Proje klasorunde ^(football-intelligence^) su dosyalara bak:
echo   baslat-hata.log    ne zaman ne oldu (olay gunlugu)
echo   derleme.log        derleme ciktisi
echo   sunucu-cikti.log   sunucunun kendi ciktisi
pause

:end
