@echo off
setlocal

cd /d "%~dp0"

echo.
echo HIDE installer
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo Installer exited with code %EXITCODE%.
    echo Right-click install.bat and choose "Run as administrator", then try again.
    echo.
    pause
    exit /b %EXITCODE%
)

endlocal
