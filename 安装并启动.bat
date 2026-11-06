@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 bootstrap.py %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo 请先安装 Python 3.10 或更新版本，并勾选 Add Python to PATH。
    echo https://www.python.org/downloads/
    pause
    exit /b 1
  )
  python bootstrap.py %*
)
set "result=%errorlevel%"
if not "%result%"=="0" pause
endlocal & exit /b %result%
