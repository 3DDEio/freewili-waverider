@echo off
setlocal
cd /d "%~dp0"
set "ENV_DIR=%~dp0.installer-venv"

if not exist "%ENV_DIR%\Scripts\python.exe" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%ENV_DIR%" || goto :error
    ) else (
        where python >nul 2>&1 || goto :error
        python -m venv "%ENV_DIR%" || goto :error
    )
)
"%ENV_DIR%\Scripts\python.exe" -c "import serial, pyfwfinder" >nul 2>&1
if errorlevel 1 (
    "%ENV_DIR%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" || goto :error
)
"%ENV_DIR%\Scripts\python.exe" "%~dp0waverider_installer.py"
exit /b %errorlevel%

:error
echo.
echo WaveRider Installer could not start. Install Python 3.11 or newer and try again.
pause
exit /b 1
