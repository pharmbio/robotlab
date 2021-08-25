#
# Startup script for webserver, to be installed and started as windows service
#
cd C:\pharmbio\robotlab-labrobots\biotek-server

echo "Activate venv"
.\venv\Scripts\Activate.ps1

echo "Start webserver"
python .\cliwrapper.py
