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

Use Windows PowerShell. Clone the git repo to the directory `C:\pharmbio\robotlab-labrobots`.

```
cd C:\pharmbio\robotlab-labrobots\biotek-server

python -m venv venv

.\venv\Scripts\Activate.ps1

# install flask
pip install -r requirements.txt
```

## Development test

You can now test the installation by starting the web server "manually".
Further down in the documentation are instructions how to setup autostart of the server.

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
# try the test endpoint `help`, which writes windows help pages to you
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

## Configure BioTek software

Make sure that this option is checked in each protocol:

<img src=images/lhc-ports.jpg>

This can be found by going to Tools > Preferences in LHC. If the other option
is checked, the program may have difficulty switching between instruments.
The error message you would get is:

> Test Communications error. Error code: 6061 Port is no longer available.

## Configure user for autostarting

Because of dialog boxes in BioTek `BTILHCRunner.dll` that are used by the
`LHC_CallerCLI.exe` the Washer and Dispenser Rest-servers can not run as
"Services" in Windows, they will render error if not running as Desktop app
on a logged in user.

The error is:

> Message - Showing a modal dialog box or form when the application is not
> running in UserInteractive mode is not a valid operation

We workaround this by running the REST-servers as programs on a logged in user.

- To allow more than one user on remote desktop at same time on Windows 10
  we are using this mod: https://github.com/stascorp/rdpwrap

- Use the _autologon_ app to enable logging in on Windows:

  <img src=images/autologon.png>

- Set never expire on windows password. Start _Computer Management_, under System Tools > Local Users and Groups > Users, check "Password never expires" under the user's properties:

  <img src="images/password-noexpire.png">

- Configure Windows Defender Firewall to allow incoming traffic to python on either all ports or 5050.

  <img src=images/firewall.png>

- Add ScheduledTasks:
    - The desktop for this user is automatically locked via a ScheduledTask being run ONLOGON
    - The REST-servers are started via a Powershell script as a ScheduledTask ONLOGON for this user

    ```
    # Create user robot-services
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

