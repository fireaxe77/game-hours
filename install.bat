@echo off
setlocal
cd /d "%~dp0"

echo Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo pip install failed. Make sure Python 3 is installed and on PATH.
    pause
    exit /b 1
)

rem pythonw.exe lives next to python.exe (no console window)
for /f "usebackq delims=" %%i in (`python -c "import os,sys;print(os.path.dirname(sys.executable))"`) do set "PYDIR=%%i"
set "GH_PYW=%PYDIR%\pythonw.exe"
set "GH_SCRIPT=%~dp0gamehours.py"
set "GH_DIR=%~dp0"
set "GH_ICON=%~dp0icon.ico"

if not exist "%GH_PYW%" (
    echo pythonw.exe not found at "%GH_PYW%"
    pause
    exit /b 1
)

echo Creating Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Game Hours.lnk'); $s.TargetPath=$env:GH_PYW; $s.Arguments=([char]34)+$env:GH_SCRIPT+([char]34); $s.WorkingDirectory=$env:GH_DIR; $s.IconLocation=$env:GH_ICON; $s.Save()"
if errorlevel 1 (
    echo Could not create the shortcut.
    pause
    exit /b 1
)

echo.
echo Done. Use the "Game Hours" shortcut on your Desktop.
pause
