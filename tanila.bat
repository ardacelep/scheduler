@echo off
REM ================================================================
REM  Staj Rotasyonu - TESHIS
REM  Bir sorun oldugunda bu dosyaya cift tiklayin, ekrandaki metnin
REM  TAMAMINI kopyalayip gonderin. Hicbir seyi degistirmez.
REM
REM  Metni kopyalamak icin: pencereye sag tiklayin -> Tumunu Sec,
REM  sonra Enter'a basin (panoya kopyalanir).
REM ================================================================
setlocal
title Staj Rotasyonu - teshis
cd /d "%~dp0"

REM Yanlis yerden calistirma korumasi: bu dosya UYGULAMA KLASORUNDE
REM olmali. GitHub'dan indirilip Masaustunden calistirilirsa yanindaki
REM scripts\ klasoru bulunmaz ve Python anlasilmaz bir hata verir.
if not exist "scripts\tanila.py" (
  echo.
  echo ================================================================
  echo  YANLIS KLASOR
  echo ================================================================
  echo  Bu dosya su an surada calisiyor:
  echo    %~dp0
  echo  Ama uygulama dosyalari burada degil.
  echo.
  echo  Bu .bat dosyasini UYGULAMANIN KURULU OLDUGU klasorden
  echo  calistirmalisiniz. Genellikle:
  echo    %USERPROFILE%\StajRotasyonu
  echo.
  echo  O klasoru acip icindeki "tanila.bat" dosyasina cift tiklayin.
  echo  ^(Buradaki kopyayi silebilirsiniz.^)
  echo ================================================================
  echo.
  pause
  exit /b 1
)

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo Sanal ortam ^(.venv^) bulunamadi - kurulum tamamlanmamis olabilir.
  echo Once "baslat.bat" dosyasina cift tiklayin.
  echo.
  echo Yine de sistemdeki Python ile denenecek:
  echo.
  set "PY=python"
)

"%PY%" scripts\tanila.py
echo.
pause
