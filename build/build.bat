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

echo [1/5] Preparing virtual environment
if not exist .venv (
    python -m venv .venv 1>>"%LOG%" 2>>&1
)
call .venv\Scripts\activate.bat 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Failed to activate venv. See %LOG%
    goto :fail
)

echo [2/5] Installing dependencies
set "NEED_DEPS="
if defined FORCE_DEPS set "NEED_DEPS=1"
if not defined NEED_DEPS python -c "import PyQt6, PyInstaller" 1>>"%LOG%" 2>>&1
if not defined NEED_DEPS if errorlevel 1 set "NEED_DEPS=1"
if defined NEED_DEPS (
    pip install --upgrade pip 1>>"%LOG%" 2>>&1
    pip install -r requirements.txt 1>>"%LOG%" 2>>&1
    pip install pyinstaller 1>>"%LOG%" 2>>&1
    if errorlevel 1 (
        echo pip install failed. See %LOG%
        goto :fail
    )
) else (
    echo     [skip] dependencies present ^(set FORCE_DEPS=1 to reinstall^)
)

echo [3/5] Cleaning output (set CLEAN=1 to also clear PyInstaller cache)
if exist dist rmdir /S /Q dist
if defined CLEAN if exist build\build rmdir /S /Q build\build
if defined CLEAN for /r %%d in (__pycache__) do if exist "%%d" rmdir /S /Q "%%d"
if defined CLEAN echo     [clean] PyInstaller cache cleared

echo [*] Character image change support (set CHARACTER_EDIT=0 to disable, 1 to enable)
if not defined CHARACTER_EDIT set /p "CHARACTER_EDIT=Allow users to change the character image in this build? (Y/n): "
set "FLAGFILE=resources\character_edit_disabled.flag"
if exist "%FLAGFILE%" del "%FLAGFILE%"
if /I "!CHARACTER_EDIT!"=="n" goto :char_disabled
if "!CHARACTER_EDIT!"=="0" goto :char_disabled
echo     -^> character change ENABLED
goto :char_done
:char_disabled
echo disabled> "%FLAGFILE%"
echo     -^> character change DISABLED (fixed default image)
:char_done

echo [4/5] Running PyInstaller
set "PI_CLEAN="
if defined CLEAN set "PI_CLEAN=--clean"
pyinstaller --noconfirm !PI_CLEAN! build\character_todo.spec 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo PyInstaller build failed. See %LOG%
    goto :fail
)
REM flag already bundled above; clean source tree so dev runs default to ENABLED
if exist "%FLAGFILE%" del "%FLAGFILE%"
echo     -^> dist\CharacterTodo.exe created  (single file, deliver this one)

echo [5/5] Optional installer (set MAKE_INSTALLER=1 to also build a setup)
if /I not "!MAKE_INSTALLER!"=="1" (
    echo     [skip] Single-exe distribution. Just hand over dist\CharacterTodo.exe
    goto :done
)
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
    echo     [skip] Inno Setup not found. Only dist\CharacterTodo.exe was created.
    echo     Install from https://jrsoftware.org/isdl.php and re-run this script.
    goto :done
)

"!ISCC!" build\installer.iss 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Inno Setup build failed. See %LOG%
    goto :fail
)
echo     -^> build\installer_out\CharacterTodo-Setup-0.3.0.exe created

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
