@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
echo 监控已启动，保持本窗口开着。命中关键字的新帖会推送到微信。按 Ctrl+C 停止。
echo.
%PY% monitor.py
pause
