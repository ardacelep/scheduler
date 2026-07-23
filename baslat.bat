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

REM Cozucu gercekten calisiyor mu? OR-Tools bazi Python surumlerinde
REM (orn. 3.14) kurulur, ice aktarilir ama COZUM ANINDA sureci sessizce
REM cokertir. Bunu simdi yakalamazsak kullanici ancak ilk rotasyon
REM denemesinde, uygulama aniden kapaninca fark eder.
echo Cozucu dogrulaniyor...
"%PY%" -c "from ortools.sat.python import cp_model; m=cp_model.CpModel(); x=m.NewIntVar(0,5,'x'); m.Add(x==3); s=cp_model.CpSolver(); s.parameters.num_workers=1; s.Solve(m)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  KURULUM TAMAMLANAMADI: cozucu bu Python surumunde calismiyor
  echo ================================================================
  for /f "delims=" %%v in ('"%PY%" -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
  echo  Kurulan Python surumu: %PYVER%
  echo.
  echo  OR-Tools kuruldu ama cozum aninda cokuyor. Cozum: Python 3.12
  echo  ile yeniden kurmak. Asagidakileri sirayla calistirin:
  echo.
  echo    winget install --id=astral-sh.uv -e
  echo    ^(sonra bu pencereyi kapatip yeni bir cmd acin^)
  echo    cd /d "%~dp0"
  echo    rmdir /s /q .venv
  echo    uv venv --python 3.12 --seed .venv
  echo    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
  echo.
  echo  Sonra bu dosyaya tekrar cift tiklayin.
  echo ================================================================
  echo.
  pause
  exit /b 1
)
echo Cozucu calisiyor.

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
