@echo off
echo ===================================================
echo  EV Assistant - Startup Installer
echo ===================================================
echo.

set VENV_PATH=%~dp0.venv\Scripts\pythonw.exe
set LISTENER_SCRIPT=%~dp0main.py

echo Creating startup shortcut for EV Background Listener...

:: Create a VBScript to create the shortcut
set VBS_FILE="%TEMP%\CreateShortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") > %VBS_FILE%
echo sLinkFile = "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EV_Listener.lnk" >> %VBS_FILE%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %VBS_FILE%
echo oLink.TargetPath = "%VENV_PATH%" >> %VBS_FILE%
echo oLink.Arguments = """%LISTENER_SCRIPT%""" >> %VBS_FILE%
echo oLink.WorkingDirectory = "%~dp0" >> %VBS_FILE%
echo oLink.IconLocation = "%~dp0web\favicon.ico" >> %VBS_FILE%
echo oLink.Description = "EV Background Voice Listener" >> %VBS_FILE%
echo oLink.WindowStyle = 7 >> %VBS_FILE%
echo oLink.Save >> %VBS_FILE%

cscript //nologo %VBS_FILE%
del %VBS_FILE%

echo.
echo ✅ Installation Complete!
echo EV will now start listening automatically in the background every time you turn on your PC.
echo If it is already running, launching again will bring the existing window to front.
echo.
echo To start it right now without restarting your PC, press any key.
pause
start "" "%VENV_PATH%" "%LISTENER_SCRIPT%"
echo Listener started in background! You can close this window.
