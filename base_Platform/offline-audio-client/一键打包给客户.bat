@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在打包 Windows 11 客户版 ZIP，请稍候...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_customer_zip.ps1"
if errorlevel 1 (
  echo.
  echo 打包失败，请根据上方红色报错处理（通常需先安装 Python 3.10+ 64 位）。
  pause
  exit /b 1
)
echo.
pause
