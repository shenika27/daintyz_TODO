@echo off
REM ============================================================
REM uninstall_all.bat - Fully remove Character TODO
REM   1) Uninstall the app (runs Inno Setup uninstaller)
REM   2) Delete user data (%APPDATA%\CharacterTodo: DB/settings/logs)
REM
REM Usage: run from the install folder (where unins000.exe is),
REM        e.g. by double-click. Autostart registry entry is
REM        removed as part of step 1.
REM ============================================================
setlocal
echo Starting full removal of Character TODO.
echo  - Uninstall app + delete all user data (%%APPDATA%%\CharacterTodo)
echo.
choice /M "Continue"
if errorlevel 2 (
    echo Cancelled.
    goto :end
)

set "APPDIR=%~dp0"
set "UNINS=%APPDIR%unins000.exe"

if exist "%UNINS%" (
    echo [1/2] Running uninstaller...
    REM /VERYSILENT: no prompts, waits until finished
    "%UNINS%" /VERYSILENT
) else (
    echo [1/2] unins000.exe not found. Either already uninstalled,
    echo       or this script is not in the install folder. Skipping.
)

echo [2/2] Deleting user data: %APPDATA%\CharacterTodo
if exist "%APPDATA%\CharacterTodo" (
    rmdir /S /Q "%APPDATA%\CharacterTodo"
    echo       Done.
) else (
    echo       Already removed.
)

echo.
echo Full removal complete.

:end
pause
endlocal
