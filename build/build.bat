@echo off
chcp 65001 >nul 2>nul
REM ============================================================
REM build.bat - Build EXE and installer on Windows
REM (콘솔 출력 한글 깨짐 방지: 이 파일은 UTF-8, chcp 65001 로 콘솔도 UTF-8)
REM Requirements: Python 3.10+ (PATH), optionally Inno Setup 6 (iscc)
REM Usage: run from project root -> build\build.bat
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set "LOG=%~dp0build_log.txt"
echo Build started > "%LOG%"

REM 버전 읽기(파일명/인스톨러 버전에 사용)
set "VERSION=0.0.0"
if exist VERSION set /p VERSION=<VERSION
echo Version: %VERSION% >> "%LOG%"

echo [1/7] Preparing virtual environment
if not exist .venv (
    python -m venv .venv 1>>"%LOG%" 2>>&1
)
call .venv\Scripts\activate.bat 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Failed to activate venv. See %LOG%
    goto :fail
)

echo [2/7] Installing dependencies
set "NEED_DEPS="
if defined FORCE_DEPS set "NEED_DEPS=1"
if not defined NEED_DEPS python -c "import PySide6, PyInstaller" 1>>"%LOG%" 2>>&1
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

echo [3/7] Cleaning output (set CLEAN=1 to also clear PyInstaller cache)
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

echo [4/7] Running PyInstaller (onedir + onefile)
set "PI_CLEAN="
if defined CLEAN set "PI_CLEAN=--clean"
set "PYINSTALLER_CMD="
set "PYINSTALLER_ARGS="
if exist ".venv\Scripts\python.exe" (
    set "PYINSTALLER_CMD=.venv\Scripts\python.exe"
    set "PYINSTALLER_ARGS=-m PyInstaller"
)
if not defined PYINSTALLER_CMD (
    where pyinstaller >nul 2>nul
    if not errorlevel 1 set "PYINSTALLER_CMD=pyinstaller"
)
if defined PYINSTALLER_CMD (
    echo Using PyInstaller: !PYINSTALLER_CMD! !PYINSTALLER_ARGS! >> "%LOG%"
    "!PYINSTALLER_CMD!" !PYINSTALLER_ARGS! --noconfirm !PI_CLEAN! build\character_todo.spec 1>>"%LOG%" 2>>&1
) else (
    echo PyInstaller not found. See dependency installation output above. >> "%LOG%"
    exit /b 1
)
if errorlevel 1 (
    echo PyInstaller build failed. See %LOG%
    goto :fail
)
REM flag already bundled above; clean source tree so dev runs default to ENABLED
if exist "%FLAGFILE%" del "%FLAGFILE%"
if not exist "dist\CharacterTodo\CharacterTodo.exe" (
    echo Expected dist\CharacterTodo\ folder was not created. See %LOG%
    goto :fail
)
if not exist "dist\CharacterTodo.exe" (
    echo Expected dist\CharacterTodo.exe was not created. See %LOG%
    goto :fail
)
echo     -^> dist\CharacterTodo\ (onedir) + dist\CharacterTodo.exe created

echo [5/7] Packaging portable ZIP (무설치판)
set "PORTABLE=dist\CharacterTodo-portable-%VERSION%.zip"
if exist "%PORTABLE%" del "%PORTABLE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\CharacterTodo' -DestinationPath '%PORTABLE%' -Force" 1>>"%LOG%" 2>>&1
if errorlevel 1 (
    echo Portable ZIP packaging failed. See %LOG%
    goto :fail
)
echo     -^> %PORTABLE% created  (압축 풀고 폴더 안 CharacterTodo.exe 실행)

echo [6/7] Building installer (설치판)
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
    echo     [skip] Inno Setup not found - 설치판 생략^(무설치 zip + onefile 은 생성됨^).
    echo     설치판도 만들려면 https://jrsoftware.org/isdl.php 설치 후 다시 실행.
) else (
    "!ISCC!" /DAppVersion=%VERSION% build\installer.iss 1>>"%LOG%" 2>>&1
    if errorlevel 1 (
        echo Inno Setup build failed. See %LOG%
        goto :fail
    )
    echo     -^> dist\CharacterTodo-Setup-%VERSION%.exe created
)

echo [7/7] Finalizing dist (중간 onedir 폴더 정리)
REM zip·설치판으로 이미 패키징된 중간 onedir 폴더는 제거(최종 산출물만 dist 에 남김)
if exist "dist\CharacterTodo" rmdir /S /Q "dist\CharacterTodo"
echo     -^> dist\CharacterTodo.exe  (단독 실행, 설치/압축해제 불필요 · 시작은 느림)

:done
echo.
echo ================ Build result ================
call :report "무설치판(zip) " "dist\CharacterTodo-portable-%VERSION%.zip" "빠른 시작"
call :report "설치판(exe)   " "dist\CharacterTodo-Setup-%VERSION%.exe" "빠른 시작, Inno Setup 필요"
call :report "onefile(exe)  " "dist\CharacterTodo.exe" "단독 실행, 시작 느림"
echo =============================================
echo See %LOG% for full output.
pause
endlocal
exit /b 0

REM 산출물 1건의 생성 여부를 표기하는 서브루틴: %1=이름 %2=경로 %3=설명
:report
if not exist "%~2" goto :report_skip
echo   [OK]   %~1: %~nx2  - %~3
exit /b 0
:report_skip
echo   [--]   %~1: 생성 안 됨  - %~3
exit /b 0

:fail
echo.
echo Build FAILED. See %LOG% for full output.
pause
endlocal
exit /b 1
