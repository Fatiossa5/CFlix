@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
  "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" -u "%~dp0server.py"
  goto end
)
py -3 -c "import sys; assert sys.version_info.major == 3 and sys.version_info.minor in range(10,100)" >nul 2>nul
if not errorlevel 1 (
  py -3 -u "%~dp0server.py"
  goto end
)
python -c "import sys; assert sys.version_info.major == 3 and sys.version_info.minor in range(10,100)" >nul 2>nul
if not errorlevel 1 (
  python -u "%~dp0server.py"
  goto end
)
echo Python 3.10 veya uzeri bulunamadi ya da calistirilamadi.
echo Python kurulumunu kontrol edin.
:end
pause
