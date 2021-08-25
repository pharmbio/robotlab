#
# Startup script for webserver (can be installed and started as windows service)
#
echo "Activate venv"
C:\pharmbio\labrobots-restserver-washer-dispenser\venv\Scripts\Activate.ps1

echo "Start webserver" >> "C:\pharmbio\labrobots-restserver-washer-dispenser\server-washer.log"
python.exe C:\pharmbio\labrobots-restserver-washer-dispenser\cliwrapper.py
