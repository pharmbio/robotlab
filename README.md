# robotlab-labrobots

Web server to our LiCONiC incubator and BioTek washer and dispenser.

This is used by the robot cellpainter, https://github.com/pharmbio/robot-cellpainter,
which is part of the AROS system, Open Automated Robotic System for Biological Laboratories,
https://github.com/pharmbio/aros.

<table>
<tr>
<td>LiCONiC incubator</td>
<td><img height=400 src=images/STX_44_BT_Flush_Front_new-tm.jpg></td>
</tr>
<tr>
<td>BioTek washer</td>
<td><img width=329 src=images/biotek-405-washer.jpg></td>
</tr>
<tr>
<td>BioTek dispenser</td>
<td><img width=329 src=images/biotek-dispenser.jpg></td>
</tr>
</table>

The setup is outlined in the schematic below, which indicates the
purpose of the three subdirectories in this repo, `biotek_repl/`, `incubator_repl/` and `labrobots_server/`.

<img src=images/overview.svg>

Since we have a C# program we will need to use a windows machine.
For simplicity, we run everything on the same windows machine.

## Installation

Install Python >= 3.10 on Windows.
Don't use the App-Store python, use the one from https://python.org.
Add executables installed by pip to your path.
Then clone this repo and run:

```
pip install --editable .
```

## Configure the Windows Firewall

Configure Windows Defender Firewall to allow incoming traffic to python on
either all ports or 5050.

<img src=images/firewall.png>

## Running

Run:

```
labrobots-server.exe
```

You can now curl it:

```
dan@NUC-robotlab:~$ curl 10.10.0.56:5050/example/flup
{
  "lines": [
    "message flup",
    "success"
  ],
  "success": true
}
dan@NUC-robotlab:~$ curl 10.10.0.56:5050/wash/TestCommunications
{
  "lines": [
    "status 1",
    "message 1 - eReady - the run completed successfully: stop polling for status",
    "success"
  ],
  "success": true
}
dan@NUC-robotlab:~$ curl 10.10.0.56:5050/disp/TestCommunications
{
  "lines": [
    "status 1",
    "message 1 - eReady - the run completed successfully: stop polling for status",
    "success"
  ],
  "success": true
}
```

## Configure BioTek software

Make sure that this option is checked in each protocol:

<img src=images/lhc-ports.jpg>

This can be found by going to Tools > Preferences in LHC. If the other option
is checked, the program may have difficulty switching between instruments.
The error message you would get is:

> Test Communications error. Error code: 6061 Port is no longer available.

