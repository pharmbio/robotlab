# LiCONiC incubator http api

<img width=250 src=images/STX_44_BT_Flush_Front_new-tm.jpg></img>

## Requirements
- Python version >= 3.6 (On Windows don´t use App-Store Python, use installer, OBS For all Usera and Tich "Add Env variables"-To make sure running as Service will work)
- venv (should be included in Python > 3.3 (if not... `sudo apt install python3.6-venv`)

## Installation and test

```
# Clone
git clone git@github.com:pharmbio/labrobots-restserver.git

cd labrobots-restserver

# Create a virtualenv for your project
python3.9 -m venv venv # on wondows python.exe -m venv .\venv
source venv/bin/activate # Or in Windows something like: .\venv\Scripts\Activate.ps

# Install python requirements
pip3 install -r requirements.txt # on windows pip3.7.exe install -r .\requirements.txt

# start server
python3 server-shaker.py # Or in Windows something like: python.exe server-shaker.py # The one on venv

#
# OBS in windows it is very important that correct pip3.7.exe and python.exe is called so venv is working...
#

# look at api in swagger ui
http://localhost:5000/ui/

# example execute program with name <name> on robot
curl -X GET --header 'Accept: application/json' 'http://localhost:5000/execute_protocol/<name>'
```

Add Systemd service

```
sudo cp shaker-robot.service /etc/systemd/system/
sudo systemctl enable shaker-robot.service
sudo systemctl start shaker-robot.service

sudo cp incubatorSTX.service /etc/systemd/system/
sudo systemctl enable incubatorSTX.service
sudo systemctl start incubatorSTX.service
```

Robot URL:s
```
http://10.10.0.56:5051/is_ready
http://10.10.0.56:5051/getClimate
http://10.10.0.56:5051/input_plate/xx
http://10.10.0.56:5051/output_plate/xx
http://10.10.0.56:5051/last_STX_response
```


