# biotek-server

Installation instructions for the BioTek server for controlling the washer and dispenser.
The server is a python flask server which calls the biotek cli executable
as a subprocess, which in turn communicates with the BioTek instruments.

<img width=250 src=images/biotek-405-washer.jpg></img>
<br><br>
<img width=250 src=images/biotek-dispenser.jpg></img>

## Requirements

Install Python >= 3.7 on Windows. Don't use the App-Store Python, use the installer.
Tick "Add Env variables" for all users in the setup program. This makes sure running as Service will work.

The instructions assume you use PowerShell. In PowerShell check what python you are using with `Get-Command python`.
Make sure you have virtualenv installed run `python -m venv`.

<img src=images/get-command.png>


## Installation

```
cd biotek-server

python -m venv venv

.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Development test

```
# make sure virtualenv is activated
.\venv\Scripts\Activate.ps1

# start server
python cliwrapper.py
```

In another terminal you can now run

```
# try the dummy help endpoint
curl.exe 'http://localhost:5050/help/ren'

# example execute program with name <name> on washer
curl 'http://localhost:5000/wash/LHC_RunProtocol/automation/8_W-4X_NoFinalAspirate.LHC'
```

Because of dialog boxes in BioTek "BTILHCRunner.dll" that are used by the "LHC_CallerCLI.exe" the Washer and Dispenser Rest-servers can not run as "Services" in Windows, they will render error if not running as Desktop app on a logged in user.
The error is:
"Message - Showing a modal dialog box or form when the application is not running in UserInteractive mode is not a valid operation"

We workaround this by running the REST-servers as programs on a logged in user.
- The user (robot-services) is auto logged in on Windows reboot via sysinternals "autologin" app
- OBS set never expire on windows password
- The desktop for this user is automatically locked via a ScheduledTask being run ONLOGON
- The REST-servers are started via a Powershell script as a ScheduledTask ONLOGON for this user
- To allow more than one user on remote desktop at same time on windows 10 we are using this mod: https://github.com/stascorp/rdpwrap

```
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


