@echo off
rem ============================================================
rem  tactic11 - masaustu kisayollarini kur.
rem
rem  NE YAPAR: Proje klasorunun BIR UST klasorune (varsayilan) kisa
rem  yonlendirici .bat dosyalari uretir - BASLAT / DURDUR / DURUM /
rem  ACILISA-EKLE / ACILISTAN-KALDIR. Her biri buradaki gercek dosyayi cagirir.
rem
rem  NEDEN YONLENDIRICI: Gercek betikler repoda (versiyonlu, satista urunle
rem  birlikte gider). Kullanici ise ust klasorden cift tiklamaya alisik ve
rem  "npm run dev" oradaki package.json'a bagli. Iki kopya tutmak yerine tek
rem  kaynak + ince yonlendirici.
rem
rem  Yol KURULUM ANINDA gomulur: proje baska bir yere tasinirsa KUR.bat'i
rem  yeniden calistir.
rem
rem  Kullanim:  KUR.bat            -> bir ust klasore kurar
rem             KUR.bat "D:\yol"   -> verilen klasore kurar
rem ============================================================
title tactic11 - kisayol kurulumu
setlocal EnableExtensions

for %%I in ("%~dp0..") do set "KOK=%%~fI"
set "HEDEF=%~1"
if not defined HEDEF for %%I in ("%KOK%\..") do set "HEDEF=%%~fI"

if not exist "%HEDEF%\" (
  echo HATA: Hedef klasor yok: %HEDEF%
  echo.
  pause
  goto :eof
)
if not exist "%~dp0BASLAT.bat" (
  echo HATA: BASLAT.bat bulunamadi. KUR.bat launcher klasorunden calistirilmali.
  echo.
  pause
  goto :eof
)

echo Kaynak : %~dp0
echo Hedef  : %HEDEF%
echo.

call :uret BASLAT
call :uret DURDUR
call :uret DURUM
call :uret ACILISA-EKLE
call :uret ACILISTAN-KALDIR

echo.
echo TAMAM. Artik su klasorden cift tiklayabilirsin:
echo   %HEDEF%
echo.
echo Not: Gercek betikler burada durur ^(football-intelligence\launcher^);
echo      yonlendiriciler yalniz onlari cagirir. Proje tasinirsa KUR.bat'i
echo      yeniden calistir.
echo.
pause
goto :eof

rem ------------------------------------------------------------
:uret
set "AD=%~1"
>"%HEDEF%\%AD%.bat" echo @echo off
>>"%HEDEF%\%AD%.bat" echo rem tactic11 - yonlendirici. KUR.bat tarafindan uretildi, elle duzenleme.
>>"%HEDEF%\%AD%.bat" echo rem Gercek dosya: %~dp0%AD%.bat
>>"%HEDEF%\%AD%.bat" echo call "%~dp0%AD%.bat" %%*
if exist "%HEDEF%\%AD%.bat" (
  echo   olusturuldu: %AD%.bat
) else (
  echo   HATA: %AD%.bat yazilamadi
)
goto :eof
