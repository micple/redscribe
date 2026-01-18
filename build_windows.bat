@echo off
setlocal enabledelayedexpansion

echo ============================================
echo    Redscribe Windows Build Script
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    pause
    exit /b 1
)

:: Check FFmpeg files
if not exist "ffmpeg\ffmpeg.exe" (
    echo [ERROR] ffmpeg\ffmpeg.exe not found
    echo Please download FFmpeg from: https://github.com/BtbN/FFmpeg-Builds/releases
    pause
    exit /b 1
)
if not exist "ffmpeg\ffprobe.exe" (
    echo [ERROR] ffmpeg\ffprobe.exe not found
    pause
    exit /b 1
)

echo [1/4] Installing/updating dependencies...
pip install pyinstaller --quiet
pip install -r requirements.txt --quiet

echo [2/4] Building executable with PyInstaller...
pyinstaller redscribe.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)

:: Check if build was successful
if not exist "dist\Redscribe\Redscribe.exe" (
    echo [ERROR] Build output not found
    pause
    exit /b 1
)

echo [3/4] Creating installer with Inno Setup...

:: Find Inno Setup
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo [WARNING] Inno Setup not found. Skipping installer creation.
    echo Download from: https://jrsoftware.org/isdl.php
    echo.
    echo Build completed without installer.
    echo You can find the portable version in: dist\Redscribe\
    pause
    exit /b 0
)

"!ISCC!" installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo    Build completed successfully!
echo ============================================
echo.
echo Installer: installer\Redscribe-Setup-1.0.0.exe
echo Portable:  dist\Redscribe\
echo.
pause
