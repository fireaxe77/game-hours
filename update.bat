@echo off
setlocal
cd /d "%~dp0"

echo Updating Game Hours...
git pull
if errorlevel 1 goto fail

python -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo Updated
pause
exit /b 0

:fail
echo.
echo Update failed - see the error above.
pause
exit /b 1
