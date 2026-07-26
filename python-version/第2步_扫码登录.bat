@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
echo 即将弹出浏览器，请扫码登录 QQ 频道，看到帖子后回到本窗口按回车...
echo.
%PY% monitor.py --setup
echo.
pause
