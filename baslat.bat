@echo off
REM ================================================================
REM  Staj Rotasyonu - BASLATMA (kaynaktan calisan kurulum icin)
REM  Bu dosyaya cift tiklayin: varsa guncellemeleri alir, uygulamayi
REM  acar. Internet yoksa mevcut surumle acilir.
REM
REM  NOT: Asil is scripts\updater.py'dedir. Bu .bat bilerek kisa
REM  tutulur cunku guncelleme bu dosyanin da uzerine yazabilir;
REM  calisan bir .bat'in uzerine yazmak tehlikelidir, Python ise
REM  bastan bellege yuklendigi icin guvenlidir.
REM ================================================================
setlocal
title Staj Rotasyonu
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if exist "%PY%" goto :calistir

echo Ilk calistirma: ortam hazirlaniyor (birkac dakika surebilir)...
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  echo.
  echo HATA: Python bulunamadi. python.org/downloads adresinden Python 3.12
  echo kurun ve kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
  echo.
  pause
  exit /b 1
)
%PYCMD% -m venv .venv
if errorlevel 1 (echo HATA: sanal ortam kurulamadi. & echo. & pause & exit /b 1)
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install --timeout 300 --retries 10 -r requirements.txt
if errorlevel 1 (
  echo.
  echo HATA: Paketler kurulamadi. Internet baglantisini kontrol edip
  echo bu dosyaya tekrar cift tiklayin - kaldigi yerden devam eder.
  echo.
  pause
  exit /b 1
)

:calistir
"%PY%" scripts\updater.py
set "SONUC=%errorlevel%"
if not "%SONUC%"=="0" (
  echo.
  echo ================================================================
  echo  UYGULAMA BEKLENMEDIK SEKILDE KAPANDI  ^(hata kodu: %SONUC%^)
  echo ================================================================
  echo  Ne olduguna dair ayrinti su dosyada:
  echo    %~dp0data\gunluk\uygulama.log
  echo.
  echo  Bu pencereyi kapatmadan once yukaridaki mesajlari okuyun ya da
  echo  ekran goruntusunu alin.
  echo ================================================================
  echo.
  pause
)
exit /b %SONUC%
