@echo off
rem ============================================================
rem  tactic11 - acilista otomatik baslatmayi kaldirir.
rem  Baslangic klasoru sabit yazilmaz (OneDrive/kurumsal profil bu yolu
rem  degistirebiliyor); ACILISA-EKLE.bat ile ayni sekilde Windows'a sorulur.
rem ============================================================
title tactic11 - acilistan kaldirma

set "STARTUP="
for /f "usebackq delims=" %%S in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetFolderPath('Startup')"`) do set "STARTUP=%%S"
if not defined STARTUP (
  echo Windows Baslangic klasoru bulunamadi - kaldirilacak bir sey yok.
  echo.
  pause
  goto :eof
)
set "HEDEF=%STARTUP%\tactic11-baslat.vbs"

if not exist "%HEDEF%" (
  echo Otomatik acilis zaten kurulu degil - degisiklik yapilmadi.
  echo.
  pause
  goto :eof
)

del "%HEDEF%" 2>nul
if exist "%HEDEF%" (
  echo HATA: Kaydi silemedim. Su dosyayi elle sil:
  echo   %HEDEF%
) else (
  echo Kaldirildi: site artik bilgisayar acilisinda otomatik baslamayacak.
  echo Elle acmak icin BASLAT.bat'a cift tikla.
)
echo.
echo Not: Su an CALISAN sunucu kapanmadi. Kapatmak icin DURDUR.bat.
echo.
pause
