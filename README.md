# Robot REST-api
This project is built upon the python-flask-swagger REST API framework **connexion**, https://github.com/zalando/connexion

Define your api-endpoints and their mapping to the python functions in `swagger-washer.yml`

Create your python functions (`washer.py`)

## Requirements
- Python version >= 3.6 (On Windows don´t use App-Store Python, use installer, OBS For all Usera and Tich "Add Env variables"-To make sure running as Service will work)
- venv (should be included in Python > 3.3 (if not... `sudo apt install python3.6-venv`)

## Installation and test
```
# Clone
git clone git@github.com:pharmbio/labrobots-restserver.git

cd labrobots-restserver

# Create a virtualenv for your project
python3 -m venv venv # on wondows python.exe -m venv .\venv
source venv/bin/activate # Or in Windows something like: .\venv\Scripts\Activate.ps

# Install python requirements
pip3 install -r requirements.txt # on windows pip3.7.exe install -r .\requirements.txt

# start server
python3 server-washer.py # Or in Windows something like: python.exe server-washer.py # The one on venv

#
# OBS in windows it is very important that correct pip3.7.exe and python.exe is called so venv is working...
#

# look at api in swagger ui
http://localhost:5000/ui/

# example execute program with id=12 on robot
curl -X GET --header 'Accept: application/json' 'http://localhost:5000/execute_prog/12'

# Add as windows service (with nssm.exe - need to be installed in "c:\pharmbio\nssm\" first)
c:\pharmbio\nssm\nssm.exe install restserver-washer powershell -File "C:\pharmbio\labrobots-restserver\start-server-washer.ps1"
c:\pharmbio\nssm\nssm.exe set restserver-washer AppStdout "C:\pharmbio\labrobots-restserver\server-washer-service.log"
c:\pharmbio\nssm\nssm.exe set restserver-washer AppStderr "C:\pharmbio\labrobots-restserver\server-washer-service.log"
c:\pharmbio\nssm\nssm.exe start restserver-washer

c:\pharmbio\nssm\nssm.exe install restserver-dispenser powershell -File "C:\pharmbio\labrobots-restserver\start-server-dispenser.ps1"
c:\pharmbio\nssm\nssm.exe set restserver-dispenser AppStdout "C:\pharmbio\labrobots-restserver\server-dispenser-service.log"
c:\pharmbio\nssm\nssm.exe set restserver-dispenser AppStderr "C:\pharmbio\labrobots-restserver\server-dispenser-service.log"
c:\pharmbio\nssm\nssm.exe start restserver-dispenser
 
```
