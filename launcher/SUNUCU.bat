@echo off
rem ============================================================
rem  tactic11 - sunucu cekirdegi (gizli calisir).
rem  Bunu dogrudan acma; BASLAT.bat veya acilis kisayolu calistirir.
rem  Hata olursa once baslat-hata.log (olay gunlugu), oradan derleme.log /
rem  sunucu-cikti.log.  Ne calisiyor sorusu icin: DURUM.bat
rem
rem  BAYATLIK KORUMASI (2026-09-09):
rem  Eskiden yalniz ".next\BUILD_ID" YOKSA derliyordu ve 3000 dinleniyorsa
rem  hic dokunmuyordu. Sonuc: kod degisse bile eski derleme sunuluyordu.
rem  Olculdu - hem frontend hem backend 16 saat boyunca bir onceki gunun
rem  kodunu sundu (/video-tracking 404 verdi) ve bunu anlamanin yolu yoktu.
rem  Artik her baslangicta KAYNAK ZAMANI ile DERLEME/SUREC ZAMANI
rem  karsilastiriliyor; eskiyse yeniden derlenip baslatiliyor.
rem
rem  -ExecutionPolicy Bypass sadece bu surece ozeldir; sistem guvenlik
rem  ayarini DEGISTIRMEZ.
rem ============================================================
title tactic11 - sunucu
rem Bu dosya launcher\ icinde; proje koku BIR UST klasordur (%~dp0..).
cd /d "%~dp0..\frontend"
rem  UC AYRI LOG - bilincli:
rem  Eskiden hepsi baslat-hata.log'a gidiyordu. "npx next start" bu dosyayi
rem  CALISTIGI SURECE acik tutuyor; ikinci bir baslatma olay satirini yazamayip
rem  "dosya baska bir islem tarafindan kullaniliyor" hatasi veriyor ve satir
rem  KAYBOLUYORDU - tani kaydi tam ihtiyac aninda eksiliyordu. Artik uzun
rem  sureli ciktilar ayri dosyalara gider; olay gunlugu hep yazilabilir kalir.
rem Gunlukler proje kokunde (api.log ile ayni yerde); *.log gitignore'da.
set LOG=%~dp0..\baslat-hata.log
set DERLEMELOG=%~dp0..\derleme.log
set SUNUCULOG=%~dp0..\sunucu-cikti.log
set PS=powershell -NoProfile -ExecutionPolicy Bypass
set GUNCEL=%PS% -File "%~dp0guncel-mi.ps1"

rem --- Frontend guncel mi?  0=guncel  1=bayat/derleme yok  2=bilinmiyor ---
%GUNCEL% -Bilesen frontend >nul 2>&1
set FE=%errorlevel%

netstat -ano | findstr LISTENING | findstr ":3000 " >nul 2>&1
set P3000=%errorlevel%

rem 3000 calisiyor VE guncel ise frontend'e dokunma; yalniz backend'i denetle.
if "%P3000%"=="0" if "%FE%"=="0" (
  call :backend
  exit /b 0
)
if "%P3000%"=="0" echo [%date% %time%] frontend BAYAT kod sunuyordu - yeniden derlenip baslatiliyor >>"%LOG%"

rem Bu projeye ait eski node sureclerini kapat (yavas dev kopyalari dahil).
%PS% -File "%~dp0sunucu-durdur.ps1" -Bilesen frontend -Sessiz >nul 2>&1
ping -n 2 127.0.0.1 >nul

rem Derleme yok ya da kaynak degismis ise derle.
if not "%FE%"=="0" (
  echo [%date% %time%] derleme baslatildi ^(kaynak degismis ya da derleme yok^) - cikti: derleme.log >>"%LOG%"
  call npm run build >"%DERLEMELOG%" 2>&1
)
if not exist ".next\BUILD_ID" (
  echo [%date% %time%] DERLEME HATASI - ayrintilar: derleme.log >>"%LOG%"
  exit /b 1
)

call :backend

rem Eski sekme/yer imleri icin ayni siteyi 3001'de de sun.
start /b "" cmd /c "npx next start -p 3001 >nul 2>&1"

rem Ana sunucu (3000). Sunucu kapanana kadar bu satirda kalir.
rem Cikti AYRI dosyaya: bu dosya sunucunun tum omru boyunca acik kalir.
echo [%date% %time%] sunucu baslatiliyor ^(3000^) - cikti: sunucu-cikti.log >>"%LOG%"
call npx next start -p 3000 >"%SUNUCULOG%" 2>&1
echo [%date% %time%] sunucu kapandi (cikis kodu %errorlevel%) >>"%LOG%"
exit /b %errorlevel%

rem ------------------------------------------------------------
rem  Backend API (port 8000) - "canli veri" sayfalari (Sozlesmeler /
rem  Bildirimler / Erisim Denetimi / Kalibrasyon) icin.
rem  OPSIYONEL: Python yoksa ya da cokerse site yine calisir (demo veriye duser).
rem  Derleme gerektirmedigi icin bayatsa kosulsuz yeniden baslatilir - ucuz.
rem ------------------------------------------------------------
:backend
%GUNCEL% -Bilesen backend >nul 2>&1
set BE=%errorlevel%
if "%BE%"=="0" goto :eof
if "%BE%"=="2" (
  echo [%date% %time%] backend durumu okunamadi - dokunulmadi >>"%LOG%"
  goto :eof
)
if not exist "%~dp0..\venv\Scripts\python.exe" (
  echo [%date% %time%] backend atlandi - venv yok ^(site demo veriyle calisir^) >>"%LOG%"
  goto :eof
)
%PS% -File "%~dp0sunucu-durdur.ps1" -Bilesen backend -Sessiz >nul 2>&1
echo [%date% %time%] backend API baslatiliyor ^(8000^) - log: football-intelligence\api.log >>"%LOG%"
rem pushd ile proje kokune gec: tum yollar goreli + BOSLUKSUZ olur,
rem boylece ic ice tirnak / "manager 2" bosluk sorunu yasanmaz.
pushd "%~dp0.."
start "" /b cmd /c "venv\Scripts\python.exe scripts\dev_api.py > api.log 2>&1"
popd
goto :eof
