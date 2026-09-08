@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"

set "PYTHON_CMD=py -3.8"
if exist "%~dp0runtime\python38\python.exe" set "PYTHON_CMD=%~dp0runtime\python38\python.exe"

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 8, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python 3.8.10。Win7 支持必须使用 Python 3.8.10 打包。
    echo 下载地址: https://www.python.org/downloads/release/python-3810/
    pause
    popd
    exit /b 1
)

if defined TARGET_BITS (
    %PYTHON_CMD% -c "import struct, sys; raise SystemExit(0 if struct.calcsize('P') * 8 == int(sys.argv[1]) else 1)" %TARGET_BITS% >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] 当前 Python 位数与 TARGET_BITS=%TARGET_BITS% 不一致。
        pause
        popd
        exit /b 1
    )
)

%PYTHON_CMD% -c "import struct; print('打包位数:', struct.calcsize('P') * 8, 'bit')"
%PYTHON_CMD% -m pip install --only-binary=:all: -r requirements.txt || goto :fail
%PYTHON_CMD% -m pip install --only-binary=:all: -r requirements-build-win7.txt || goto :fail
%PYTHON_CMD% -m pip check || goto :fail
set "EMBEDDED_CONFIG=%~dp0data\config.json"
if not exist "%EMBEDDED_CONFIG%" set "EMBEDDED_CONFIG=%~dp0data\config.example.json"
%PYTHON_CMD% -m PyInstaller --noconfirm --clean --onefile --windowed --specpath build --workpath build --distpath dist --additional-hooks-dir "%~dp0hooks" --name TeachBuddy --add-data "%~dp0app\resources;app\resources" --add-data "%EMBEDDED_CONFIG%;embedded_defaults" main.py || goto :fail

echo.
echo 打包完成: dist\TeachBuddy.exe
echo 请先在 Win7 SP1 实机测试后再分发。
pause
popd
exit /b 0

:fail
echo [ERROR] 构建失败，请先解决上方错误。
pause
popd
exit /b 1
