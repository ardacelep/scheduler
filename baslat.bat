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
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  echo.
  echo HATA: Python bulunamadi. python.org/downloads adresinden Python 3.11
  echo kurun ve kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)
%PYCMD% -m venv .venv || (echo HATA: sanal ortam kurulamadi. & pause & exit /b 1)
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt --quiet || (echo HATA: paketler kurulamadi. Internet baglantisini kontrol edin. & pause & exit /b 1)

:calistir
"%PY%" scripts\updater.py || pause & exit /b
