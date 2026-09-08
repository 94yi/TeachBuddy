@echo off
setlocal EnableExtensions
pushd "%~dp0"

set "ISCC=%~dp0tools\InnoSetup6\ISCC.exe"

if not exist "dist\TeachBuddy.exe" (
    echo [ERROR] dist\TeachBuddy.exe is missing. Run build_exe.bat first.
    popd
    exit /b 1
)

if not exist "%ISCC%" (
    echo [ERROR] Inno Setup 6 compiler was not found.
    echo Download: https://jrsoftware.org/isdl.php
    popd
    exit /b 1
)

"%ISCC%" "%~dp0installer\setup.iss"
if errorlevel 1 (
    echo [ERROR] Installer build failed.
    popd
    exit /b 1
)

echo Installer created: installer\Output\TeachBuddySetup.exe
popd
exit /b 0
