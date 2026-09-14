@echo off
chcp 65001 >nul
title 原神日常 - BetterGI 一条龙
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [权限] 需要管理员权限，正在请求提权，请在弹窗中点击"是"...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  原神日常自动化 - BetterGI 一条龙
echo  开始时间: %date% %time%
echo.
echo  注意: 运行期间请不要动鼠标键盘, 不要遮挡游戏窗口,
echo        默认运行 core 日常, 具体状态见结果文件。
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_daily.ps1"
set "workflowExit=%errorlevel%"
echo.
if "%workflowExit%"=="0" (
  echo 流程已通过核验。结果见 results.json。
) else (
  echo 未通过或尚待核实，退出码：%workflowExit%。请查看 results.json 和 logs\runs。
)
pause
exit /b %workflowExit%
