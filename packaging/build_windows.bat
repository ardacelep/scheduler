@echo off
REM ===================================================================
REM  Staj Rotasyonu - Windows .exe uretme (tek tikla)
REM  Bu dosyaya cift tiklayin. Sonuc: dist\StajRotasyonu klasoru ve
REM  dist\StajRotasyonu-windows.zip (son kullaniciya verilecek dosya).
REM  Not: Bu dosya sadece GELISTIRICI icindir; son kullanici calistirmaz.
REM ===================================================================
setlocal enabledelayedexpansion
title Staj Rotasyonu - derleme
cd /d "%~dp0.."

echo.
echo [1/5] Python araniyor...
set "PYCMD="
py -3.11 --version >nul 2>&1
if %errorlevel%==0 set "PYCMD=py -3.11"
if not defined PYCMD (
  py -3 --version >nul 2>&1
  if !errorlevel!==0 set "PYCMD=py -3"
)
if not defined PYCMD (
  python --version >nul 2>&1
  if !errorlevel!==0 set "PYCMD=python"
)
if not defined PYCMD (
  echo.
  echo HATA: Python bulunamadi.
  echo python.org/downloads adresinden Python 3.11 kurup tekrar deneyin.
  echo Kurulum sirasinda "Add python.exe to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)
echo       %PYCMD%

echo.
echo [2/5] Derleme ortami hazirlaniyor (.venv-build)...
if not exist ".venv-build\Scripts\python.exe" (
  %PYCMD% -m venv .venv-build || goto :fail
)
call ".venv-build\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto :fail
call ".venv-build\Scripts\python.exe" -m pip install -r requirements-build.txt --quiet || goto :fail

echo.
echo [3/5] Testler calistiriliyor...
call ".venv-build\Scripts\python.exe" -m pytest -q
if errorlevel 1 (
  echo.
  echo UYARI: Testler basarisiz. Yine de derlemek icin bir tusa basin,
  echo        vazgecmek icin bu pencereyi kapatin.
  pause
)

echo.
echo [4/5] .exe uretiliyor (birkac dakika surebilir)...
if exist "dist\StajRotasyonu" rmdir /s /q "dist\StajRotasyonu"
call ".venv-build\Scripts\pyinstaller.exe" --noconfirm --clean packaging\rotasyon.spec || goto :fail

echo.
echo [5/5] Kullanici dosyalari ve zip hazirlaniyor...
copy /y "packaging\OKU-BENI.txt" "dist\StajRotasyonu\OKU-BENI.txt" >nul
copy /y "packaging\Masaustune kisayol olustur.bat" "dist\StajRotasyonu\" >nul
if exist "dist\StajRotasyonu-windows.zip" del "dist\StajRotasyonu-windows.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\StajRotasyonu' -DestinationPath 'dist\StajRotasyonu-windows.zip'" || goto :fail

echo.
echo ===================================================================
echo  TAMAM.
echo  Klasor : dist\StajRotasyonu\Staj Rotasyonu.exe
echo  Paket  : dist\StajRotasyonu-windows.zip  (kullaniciya bunu verin)
echo ===================================================================
pause
exit /b 0

:fail
echo.
echo HATA: Derleme tamamlanamadi. Yukaridaki mesaji kontrol edin.
pause
exit /b 1
