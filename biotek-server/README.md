# Robot REST-api outline
The goal of this project is to provide a unified REST-api to all robots in the AROS system. The REST Api will wrap around various existing or non-existing vendor-specific api:s for communication.

## Robots
<img width=250 src=images/biotek-405-washer.jpg></img>
<br><br>
<img width=250 src=images/biotek-dispenser.jpg></img>

## Requirements
- Python version >= 3.6 (On Windows don´t use App-Store Python, use installer, OBS For all Usera and Tich "Add Env variables"-To make sure running as Service will work)
- venv (should be included in Python > 3.3 (if not... `sudo apt install python3.6-venv`)

## Installation and test
```
# Clone
git clone git@github.com:pharmbio/labrobots-restserver-washer-dispenser.git

cd labrobots-restserver-washer-dispenser

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

# example execute program with name <name> on robot
curl -X GET --header 'Accept: application/json' 'http://localhost:5000/execute_protocol/<name>'


Because of dialog boxes in BioTek "BTILHCRunner.dll" that are used by the "LHC_CallerCLI.exe" the Washer and Dispenser Rest-servers can not run as "Services" in Windows, they will render error if not running as Desktop app on a logged in user.
The error is:
"Message - Showing a modal dialog box or form when the application is not running in UserInteractive mode is not a valid operation"

We workaround this by running the REST-servers as programs on a logged in user.
- The user (robot-services) is auto logged in on Windows reboot via sysinternals "autologin" app
- OBS set never expire on windows password
- The desktop for this user is automatically locked via a ScheduledTask being run ONLOGON
- The REST-servers are started via a Powershell script as a ScheduledTask ONLOGON for this user
- To allow more than one user on remote desktop at same time on windows 10 we are using this mod: https://github.com/stascorp/rdpwrap

# Create user  robot-services
net user robot-services <password-here> /add
net localgroup administrators robot-services /add

# Log in with user and click all Windows welcome-setup-dialogs and Download and run Sysinternals program 'autologin'

# Create SceduledTask for auto lock-screen when user robot-services ONLOGON
SchTasks /CREATE /TN autolock-on-login /RU robot-services /SC ONLOGON /TR "rundll32 user32.dll, LockWorkStation"

# Create dispenser REST-server SceduledTask autostart when robot-services user ONLOGON
SchTasks /CREATE /TN restserver-dispenser-autostart-on-login /RU robot-services /SC ONLOGON /TR "Powershell.exe -ExecutionPolicy Bypass C:\pharmbio\labrobots-restserver-washer-dispenser\start-server-dispenser.ps1 -RunType $true -Path C:\pharmbio\labrobots-restserver-washer-dispenser"

# Create washer REST-server SceduledTask autostart when robot-services user ONLOGON
SchTasks /CREATE /TN restserver-washer-autostart-on-login /RU robot-services /SC ONLOGON /TR "Powershell.exe -ExecutionPolicy Bypass C:\pharmbio\labrobots-restserver-washer-dispenser\start-server-washer.ps1 -RunType $true -Path C:\pharmbio\labrobots-restserver-washer-dispenser"

# The tasks above are now started when "ANY" user logs on, to change this to robot-services user only: Start TaskScheduler and edit these 2 tasks manually Task->Triggers>Edit->SpecifficUser->robot-services

# SchTasks /DELETE /TN autolock-on-login
# SchTasks /DELETE /TN restserver-dispenser-autostart-on-login
# SchTasks /DELETE /TN restserver-washer-autostart-on-login

```
Windows firewall
In windows firewall configure:
- Allow incoming traffic to Python.exe
- Allow incoming traffic to port 5000-5001


Robot URL:s
```
## Washer
http://washer.lab.pharmb.io:5000/is_ready
http://washer.lab.pharmb.io:5000/status
http://washer.lab.pharmb.io:5000/execute_protocol/test-protocols\washer_prime_buffers_A_B_C_D_25ml.LHC

## Dispenser
http://dispenser.lab.pharmb.io:5001/is_ready
http://dispenser.lab.pharmb.io:5001/status
http://dispenser.lab.pharmb.io:5001/execute_protocol/test-protocols/dispenser_prime_all_buffers.LHC


