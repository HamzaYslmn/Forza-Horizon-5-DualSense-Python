@echo off
setlocal enabledelayedexpansion

where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found.
    set /p "answer=uv will be installed (https://astral.sh/uv/). Do you allow downloading it? Y/n: "

    if /I "!answer!"=="n" (
        python -m pip install uv
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    )

    where uv >nul 2>nul
    if errorlevel 1 (
        echo uv was installed but could not be found in this session.
        echo Please add uv to your PATH or restart your terminal.
        pause
        exit /b 1
    )
)

cd /d "%~dp0src"

if "%~1"=="" (
    uv run main.py
    if !errorlevel! neq 0 (
        echo.
        echo Application exited with error code !errorlevel!.
        pause
    )
    pause
) else (
    :: Steam wrapper. Prefer Windows Terminal (Win11 native) when available.
    where wt >nul 2>nul
    if !errorlevel! equ 0 (
        start "" wt.exe new-tab --title "FH5 DualSense" -d "%~dp0src" cmd /c "uv run main.py"
    ) else (
        start "FH5 DualSense" /MIN uv run main.py
    )
    start "" %*
    exit /b 0
)
