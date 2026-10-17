@echo off
cd /d "%~dp0"
title CFlix - Gmail kurulumu
echo CFlix Gmail kurulum penceresi aciliyor...
if not exist "%~dp0setup_gmail_window.py" (
  echo Kurulum dosyasi eksik: setup_gmail_window.py
  goto end
)
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" -u "%~dp0setup_gmail_window.py" %*
  goto end
)
py -3 -c "import sys; assert sys.version_info.major == 3 and sys.version_info.minor in range(10,100)" >nul 2>nul
if not errorlevel 1 (
  py -3 -u "%~dp0setup_gmail_window.py" %*
  goto end
)
python -c "import sys; assert sys.version_info.major == 3 and sys.version_info.minor in range(10,100)" >nul 2>nul
if not errorlevel 1 (
  python -u "%~dp0setup_gmail_window.py" %*
  goto end
)
echo Python 3.10 veya uzeri bulunamadi ya da calistirilamadi.
echo Python kurulumunu kontrol edin. Bu pencere Gmail kurulumuna aittir.
:end
pause
