#
# Startup script for webserver (can be installed and started as windows service)
#
echo "Activate venv"
C:\pharmbio\labrobots-restserver\venv\Scripts\Activate.ps1

echo "Start webserver" >> "C:\pharmbio\labrobots-restserver\server-washer.log"
python.exe C:\pharmbio\labrobots-restserver\server-washer.py