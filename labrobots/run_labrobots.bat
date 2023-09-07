:: Hand over to windows terminal (wt) which does not block the process when selecting text

echo cd /robotlab/labrobots > temp_loop.bat
echo :loop >> temp_loop.bat
echo call labrobots.exe >> temp_loop.bat
echo goto loop >> temp_loop.bat

wt -p "Command Prompt" -d /robotlab/labrobots cmd.exe /K temp_loop.bat
