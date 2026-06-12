@echo off
REM ============================================================
REM build.bat - Build EXE and installer on Windows
REM Requirements: Python 3.10+ (PATH), optionally Inno Setup 6 (iscc)
REM Usage: run from project root -> build\build.bat
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set "LOG=%~dp0build_log.txt"
echo Build started > "%LOG%"

echo [1/4] Preparing virtual environment
if not exist .venv (
    python -m venv .venv 1>>"%LOG%" 2>>&1
)
call .venv\Scripts\activate.bat 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Failed to activate venv. See %LOG%
    goto :fail
)

echo [2/4] Installing dependencies
pip install --upgrade pip 1>>"%LOG%" 2>>&1
pip install -r requirements.txt 1>>"%LOG%" 2>>&1
pip install pyinstaller 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo pip install failed. See %LOG%
    goto :fail
)

echo [3/4] Running PyInstaller
pyinstaller --noconfirm --clean build\character_todo.spec 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo PyInstaller build failed. See %LOG%
    goto :fail
)
echo     -^> dist\CharacterTodo\CharacterTodo.exe created

echo [4/4] Building installer with Inno Setup
set "ISCC="
where iscc >nul 2>nul
if not errorlevel 1 (
    set "ISCC=iscc"
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo     [skip] Inno Setup not found. Only the EXE above was created.
    echo     Install from https://jrsoftware.org/isdl.php and re-run this script.
    goto :done
)

"!ISCC!" build\installer.iss 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Inno Setup build failed. See %LOG%
    goto :fail
)
echo     -^> build\installer_out\CharacterTodo-Setup-0.1.0.exe created

:done
echo.
echo Done. See %LOG% for full output.
pause
endlocal
exit /b 0

:fail
echo.
echo Build FAILED. See %LOG% for full output.
pause
endlocal
exit /b 1
