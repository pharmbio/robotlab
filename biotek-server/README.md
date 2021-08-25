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

# install flask
pip install -r requirements.txt
```

## Development test

```
# make sure virtualenv is activated
.\venv\Scripts\Activate.ps1

# start server
python cliwrapper.py

# by default it runs on 10.10.0.56:5050, but this can be overriden:
$env:HOST = '0.0.0.0'; python cliwrapper.py
$env:PORT = '13337'; python cliwrapper.py
```

In another terminal you can now curl to it.

```
# try the dummy help endpoint
curl.exe 'http://10.10.0.56:5050/help/ren'

# execute test program on washer
# make sure you have a plate in washer and D bottle with something like destilled water or PBS
curl 'http://10.10.0.56:5000/wash/LHC_RunProtocol/automation/2_4_6_W-3X_FinalAspirate_test.LHC
```

Note that you cannot curl to `localhost` unless you change the HOST env var to `127.0.0.1` or `0.0.0.0`.

Example output from the `help` test endpoint, using devserver as jumphost:

```
$ ssh devserver curl 10.10.0.56:5050/help/ren 2>/dev/null | jq --raw-output .out
Renames a file or files.

RENAME [drive:][path]filename1 filename2.
REN [drive:][path]filename1 filename2.

Note that you cannot specify a new drive or path for your destination file.
```

## Configuring user for autostarting

Because of dialog boxes in BioTek `BTILHCRunner.dll` that are used by the
`LHC_CallerCLI.exe` the Washer and Dispenser Rest-servers can not run as
"Services" in Windows, they will render error if not running as Desktop app
on a logged in user.

The error is:

> Message - Showing a modal dialog box or form when the application is not
> running in UserInteractive mode is not a valid operation

We workaround this by running the REST-servers as programs on a logged in user.
- The user (robot-services) is auto logged in on Windows reboot via sysinternals "autologin" app
- Set never expire on windows password
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

### Configure windows firewall

In windows firewall configure:
- Allow incoming traffic to Python.exe
- Allow incoming traffic to port 5000-5001


