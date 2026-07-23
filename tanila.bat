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
