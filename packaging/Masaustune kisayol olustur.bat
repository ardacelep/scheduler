@echo off
REM Masaustune "Staj Rotasyonu" kisayolu olusturur.
REM Bu dosyaya bir kez cift tiklamaniz yeterlidir.
setlocal
set "HEDEF=%~dp0Staj Rotasyonu.exe"

if not exist "%HEDEF%" (
  echo.
  echo "Staj Rotasyonu.exe" bu klasorde bulunamadi.
  echo Bu dosyayi uygulamanin bulundugu klasorden calistirin.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Staj Rotasyonu.lnk');" ^
  "$s.TargetPath='%HEDEF%';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%HEDEF%,0';" ^
  "$s.Description='Staj Rotasyonu';" ^
  "$s.Save()"

if errorlevel 1 (
  echo Kisayol olusturulamadi.
  pause
  exit /b 1
)

echo.
echo Masaustunde "Staj Rotasyonu" kisayolu olusturuldu.
echo Bundan sonra uygulamayi oradan acabilirsiniz.
echo.
pause
