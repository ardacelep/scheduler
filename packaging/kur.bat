@echo off
REM ================================================================
REM  Staj Rotasyonu - ILK KURULUM (kaynaktan, guncellenebilir)
REM  Bu dosyayi GELISTIRICI, hedef bilgisayarda BIR KEZ calistirir.
REM  Gerekenler: internet + git + Python 3.11 (ikisi de kurulu olmali).
REM
REM  Yapilanlar:
REM    1) Depo %USERPROFILE%\StajRotasyonu klasorune klonlanir
REM    2) Sanal ortam kurulur, paketler yuklenir
REM    3) Masaustune "Staj Rotasyonu" kisayolu konur (baslat.bat)
REM
REM  Ozel (private) depo icin URL'ye salt-okunur token gomun:
REM    https://x-access-token:TOKEN@github.com/KULLANICI/DEPO.git
REM  Token yalnizca .git\config icinde durur, betiklerde yer almaz.
REM ================================================================
setlocal
title Staj Rotasyonu - kurulum

set "HEDEF=%USERPROFILE%\StajRotasyonu"

git --version >nul 2>&1 || (
  echo HATA: git kurulu degil. git-scm.com/download/win adresinden kurun.
  pause & exit /b 1
)
set "PYCMD="
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  echo HATA: Python bulunamadi. python.org/downloads adresinden 3.11 kurun
  echo ve "Add python.exe to PATH" kutusunu isaretleyin.
  pause & exit /b 1
)

if exist "%HEDEF%\.git" (
  echo "%HEDEF%" zaten kurulu. Guncellemek icin oradaki guncelle.bat yeterli.
  pause & exit /b 0
)

set /p REPO_URL="Depo adresi (https://...git): "
if "%REPO_URL%"=="" (echo Adres girilmedi. & pause & exit /b 1)

echo.
echo [1/3] Depo indiriliyor...
git clone "%REPO_URL%" "%HEDEF%" || (echo HATA: klonlama basarisiz. Adresi/tokeni kontrol edin. & pause & exit /b 1)

echo.
echo [2/3] Ortam kuruluyor (birkac dakika surebilir)...
cd /d "%HEDEF%"
%PYCMD% -m venv .venv || (echo HATA: sanal ortam kurulamadi. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet || (echo HATA: paket kurulumu basarisiz. & pause & exit /b 1)

echo.
echo [3/3] Masaustu kisayolu olusturuluyor...
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Staj Rotasyonu.lnk');" ^
  "$s.TargetPath='%HEDEF%\baslat.bat';" ^
  "$s.WorkingDirectory='%HEDEF%';" ^
  "$s.IconLocation='%SystemRoot%\System32\shell32.dll,21';" ^
  "$s.Description='Staj Rotasyonu';" ^
  "$s.Save()"

echo.
echo ================================================================
echo  KURULUM TAMAM.
echo  Kullanici bundan sonra masaustundeki "Staj Rotasyonu"
echo  kisayoluna cift tiklar; uygulama her acilista GitHub'dan
echo  guncellemeleri kendi alir.
echo ================================================================
pause
