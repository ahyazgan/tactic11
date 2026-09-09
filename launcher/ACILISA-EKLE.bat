@echo off
rem ============================================================
rem  tactic11 - bilgisayar acilisinda sitenin otomatik hazir olmasini saglar.
rem  BIR KEZ cift tiklaman yeterli.  Vazgecmek icin: ACILISTAN-KALDIR.bat
rem
rem  NEDEN KOPYALAMIYOR DA URETIYOR (2026-09-09):
rem  Eskiden baslat-gizli.vbs dogrudan Baslangic klasorune KOPYALANIYORDU ve
rem  icindeki proje yolu SABIT GOMULUYDU. Proje klasoru tasinirsa, adi
rem  degisirse ya da baska bir bilgisayara kurulursa otomatik acilis SESSIZCE
rem  kirilirdi - pencere gizli oldugu icin hata bile gorunmezdi. Artik kayit
rem  kurulum anindaki GERCEK yol ile uretiliyor.
rem
rem  Baslangic klasoru de sabit yazilmiyor: OneDrive/kurumsal profil
rem  yonlendirmesi bu yolu degistirebiliyor, Windows'a kendisi sordurulur.
rem ============================================================
title tactic11 - acilisa ekleme

if not exist "%~dp0SUNUCU.bat" (
  echo HATA: SUNUCU.bat bulunamadi.
  echo Bu dosya proje klasorunun icinden calistirilmalidir.
  echo.
  pause
  goto :eof
)

set "STARTUP="
for /f "usebackq delims=" %%S in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetFolderPath('Startup')"`) do set "STARTUP=%%S"
if not defined STARTUP goto nostartup
if not exist "%STARTUP%" goto nostartup
set "HEDEF=%STARTUP%\tactic11-baslat.vbs"

>"%HEDEF%" echo ' tactic11 - bilgisayar acilisinda siteyi gizli baslatir.
>>"%HEDEF%" echo ' ACILISA-EKLE.bat tarafindan uretildi - elle duzenleme.
>>"%HEDEF%" echo ' Kaldirmak icin proje klasorundeki ACILISTAN-KALDIR.bat'a cift tikla.
>>"%HEDEF%" echo Set sh = CreateObject^("WScript.Shell"^)
>>"%HEDEF%" echo sh.Run """%~dp0SUNUCU.bat""", 0, False

if not exist "%HEDEF%" (
  echo HATA: Eklenemedi - Baslangic klasorune yazma izni yok gibi gorunuyor.
  echo   %STARTUP%
  echo.
  pause
  goto :eof
)

echo TAMAM: Bilgisayar her acildiginda site otomatik hazir olacak.
echo.
for %%I in ("%~dp0..") do set "KOK=%%~fI"
echo   Proje klasoru : %KOK%
echo   Acilis kaydi  : %HEDEF%
echo.
echo Not: Acilista kod degismisse once yeniden derlenir; site birkac dakika
echo      sonra hazir olur. Derleme gerekmiyorsa saniyeler icinde acilir.
echo.
echo Vazgecersen ACILISTAN-KALDIR.bat'a cift tikla.
echo.
pause
goto :eof

:nostartup
echo HATA: Windows Baslangic klasoru bulunamadi.
echo Otomatik acilis eklenemedi; siteyi BASLAT.bat ile elle acabilirsin.
echo.
pause
