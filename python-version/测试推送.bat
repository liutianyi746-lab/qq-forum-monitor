@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
echo 正在发送一条测试推送，检查微信能否收到...
echo.
%PY% monitor.py --test-push
echo.
pause
