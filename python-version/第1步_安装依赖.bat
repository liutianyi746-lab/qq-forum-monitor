@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
echo 正在安装依赖，第一次会下载浏览器，约需 1-2 分钟，请耐心等待...
echo.
%PY% -m pip install -r requirements.txt
%PY% -m playwright install chromium
echo.
echo ============ 安装完成 ============
echo 下一步：双击运行  第2步_扫码登录.bat
echo.
pause
