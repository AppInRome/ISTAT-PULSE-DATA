@echo off
setlocal EnableExtensions
title ISTAT PULSE - Compila APK Android
cd /d "%~dp0"
echo.
echo ===========================================
echo   ISTAT PULSE - COMPILAZIONE APK DEBUG
echo ===========================================
echo.
if not exist "settings.gradle" if not exist "settings.gradle.kts" goto :missingproject
if not exist "gradlew.bat" goto :missingwrapper
if not exist "gradle\wrapper\gradle-wrapper.jar" goto :missingjar
if not exist "app\build.gradle" if not exist "app\build.gradle.kts" goto :missingapp
where java >nul 2>&1
if errorlevel 1 (
  if not defined JAVA_HOME goto :nojava
  if not exist "%JAVA_HOME%\bin\java.exe" goto :nojava
)
if not defined ANDROID_HOME if not defined ANDROID_SDK_ROOT (
  if exist "%LOCALAPPDATA%\Android\Sdk\platforms" (
    set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
    set "ANDROID_SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
  ) else goto :nosdk
)
echo Progetto: %CD%
echo Compilo con Gradle Wrapper senza cancellare dati e sorgenti...
echo.
call "%~dp0gradlew.bat" --no-daemon --stacktrace :app:assembleDebug
if errorlevel 1 goto :failed
set "APK=app\build\outputs\apk\debug\app-debug.apk"
if not exist "%APK%" goto :missingapk
if not exist "APK_GENERATA" mkdir "APK_GENERATA"
copy /Y "%APK%" "APK_GENERATA\ISTAT_PULSE_DEBUG.apk" >nul
if errorlevel 1 goto :failed
echo.
echo ===========================================
echo     APK COMPILATA CORRETTAMENTE
echo ===========================================
echo.
echo File: %CD%\APK_GENERATA\ISTAT_PULSE_DEBUG.apk
echo.
echo NOTA: questa e' una build DEBUG, firmata con la chiave
echo di debug locale. Non sostituisce una release firmata.
echo.
pause
exit /b 0

:missingproject
echo ERRORE: file settings.gradle / settings.gradle.kts mancante.
echo Metti questo BAT nella cartella principale del progetto ANDROID PULSE.
goto :exitfail
:missingwrapper
echo ERRORE: gradlew.bat mancante. Archivio Android incompleto.
goto :exitfail
:missingjar
echo ERRORE: gradle\wrapper\gradle-wrapper.jar mancante.
goto :exitfail
:missingapp
echo ERRORE: app\build.gradle (.kts) mancante.
goto :exitfail
:nojava
echo ERRORE: Java JDK non trovato. Installa il JDK richiesto dal progetto.
goto :exitfail
:nosdk
echo ERRORE: Android SDK non trovato.
echo Installa Android Studio e Android SDK, poi riprova.
goto :exitfail
:missingapk
echo ERRORE: Gradle non ha prodotto app-debug.apk nel percorso previsto.
goto :exitfail
:failed
echo.
echo COMPILAZIONE NON RIUSCITA. Leggi gli errori sopra.
:exitfail
echo.
pause
exit /b 1
