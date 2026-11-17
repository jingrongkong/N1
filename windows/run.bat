@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 抖音直播福袋自动化 - 一键入口
rem 双击本文件 = 体检 + 起 WDA 代理 + 开跑
rem 其它用法： run.bat doctor / run.bat probe / run.bat mock

python go.py %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo 退出码 %RC%
  pause
)
