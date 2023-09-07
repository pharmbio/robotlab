:: Hand over to windows terminal (wt) which does not block the process when selecting text

echo cd /robotlab/labrobots > temp_loop.bat
echo :loop >> temp_loop.bat
echo call labrobots.exe >> temp_loop.bat
echo goto loop >> temp_loop.bat

:: Try running wt to see if it exists
wt --version >nul 2>nul
if errorlevel 1 (
    :: wt doesn't exist
    :: this is for the GBG computer
    temp_loop.bat
) else (
    :: wt exists, use it
    wt -p "Command Prompt" -d /robotlab/labrobots cmd.exe /K temp_loop.bat
)
