@echo off
setlocal EnableExtensions
title ISTAT PULSE - CREA RAR WINDOWS
cd /d "%~dp0"
echo.
echo CREA ARCHIVIO RAR DEL PROGETTO ANDROID PULSE
echo.
if not exist "settings.gradle" if not exist "settings.gradle.kts" goto :noproject
if not exist "gradlew.bat" goto :noproject
if not exist "COMPILA_APK.bat" goto :nobat
set "RAR=%ProgramFiles%\WinRAR\Rar.exe"
if not exist "%RAR%" set "RAR=%ProgramFiles(x86)%\WinRAR\Rar.exe"
if not exist "%RAR%" goto :norarexe
set "OUT=%~dp0..\PULSE_ANDROID_COMPLETO_CON_BAT.rar"
echo Creo: %OUT%
"%RAR%" a -r -m3 -ep1 -x*.apk -x*.aab -x*.jks -x*.keystore -x*.env -xlocal.properties -x.gradle\* -x.idea\* -x.git\* -xapp\build\* -xbuild\* "%OUT%" ".\*"
if errorlevel 1 goto :failed
"%RAR%" t "%OUT%"
if errorlevel 1 goto :failed
echo.
echo ARCHIVIO RAR VERIFICATO: %OUT%
echo.
pause
exit /b 0
:noproject
echo ERRORE: questo BAT deve stare nella cartella RADICE del progetto PULSE Android completo.
goto :failed
:nobat
echo ERRORE: prima copia COMPILA_APK.bat nella radice del progetto.
goto :failed
:norarexe
echo ERRORE: WinRAR non installato. E' necessario Rar.exe, non 7-Zip.
goto :failed
:failed
echo.
echo ARCHIVIO RAR NON CREATO O NON VERIFICATO.
pause
exit /b 1
