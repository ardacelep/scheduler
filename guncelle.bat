@echo off
REM ================================================================
REM  Staj Rotasyonu - SADECE GUNCELLE (uygulamayi baslatmaz)
REM  Normalde gerekmez: "baslat.bat" zaten her acilista gunceller.
REM  Telefonla "guncelle.bat'a cift tikla" demek icin vardir.
REM ================================================================
setlocal
title Staj Rotasyonu - guncelleme
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Once "baslat.bat" dosyasina cift tiklayarak kurulumu tamamlayin.
  pause
  exit /b 1
)

"%PY%" scripts\updater.py --sadece-guncelle & pause & exit /b
