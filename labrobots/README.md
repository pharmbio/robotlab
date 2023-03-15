# labrobots

Web server to our LiCONiC incubator, LiCONiC fridge, and BioTek washer,
BioTek dispenser, ImageXpress microscope, BlueCatBio BlueWash and Honeywell barcode scanner.

This is used by the robot cellpainter and the robot imager.
This is part of the AROS system, Open Automated Robotic System for Biological Laboratories,
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

Install git to clone the repo.
Clone with the access token from https://github.com/settings/tokens?type=beta
A copy is put in our password managing system.

```
git clone https://oauth2:github_pat_<TOKEN>@github.com/pharmbio/robotlab.git
```

Install Python >= 3.8 on Windows.
Don't use the App-Store python, use the one from https://python.org.
Make sure executables installed by pip are added to your path.

Now install using pip:

```
pip install --editable .
```

No need to use the foreach script, this repo has no internal dependencies.

## Configure the Windows Firewall

Configure Windows Defender Firewall to allow incoming traffic to python on
either all ports or 5050.

<img src=images/firewall.png>

## Test running

Run:

```
labrobots --test
```

or on windows:

```
labrobots.exe --test
```

The output should look like this:

```
$ labrobots --test
node_name: example
machines:
    echo: Echo()
    git: Git()
    dir_list: DirList(root_dir='.', ext='py', enable_hts_mod=True)
 * Serving Flask app 'labrobots.machine' (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://127.0.0.1:5050/ (Press CTRL+C to quit)
```

You can now curl it:

```
$ curl localhost:5050/echo/echo/banana/split?servings=3
{
  "value": "echo ('banana', 'split') {'servings': 3}"
}
```

## Running

Run:

```
while (1) { labrobots.exe }
```

The output should look like this (on the WINDOWS-GBG computer):

```
C:\pharmbio\robotlab-labrobots>labrobots-server.exe
 * Serving Flask app 'labrobots_server.main' (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
0.282 incu ready
0.766 dir_list ready
0.797 example ready
1.125 disp ready
1.125 wash ready
 * Running on http://10.10.0.56:5050/ (Press CTRL+C to quit)
```

You can now curl it:

```
dan@NUC-robotlab:~$ curl 10.10.0.97:5050
{
  "http://10.10.0.97:5050/echo": "Echo()",
  "http://10.10.0.97:5050/git": "Git()",
  "http://10.10.0.97:5050/fridge": "STX()",
  "http://10.10.0.97:5050/barcode": "BarcodeReader(last_seen={'barcode': '', 'date': ''})",
  "http://10.10.0.97:5050/imx": "IMX()"
}
dan@NUC-robotlab:~$ curl 10.10.0.97:5050/imx
{
  "http://10.10.0.97:5050/imx/send": [
    "send(self, cmd: str, *args: str)"
  ],
  "http://10.10.0.97:5050/imx/online": [
    "online(self)"
  ],
  "http://10.10.0.97:5050/imx/status": [
    "status(self)"
  ],
  "http://10.10.0.97:5050/imx/goto": [
    "goto(self, pos: str)"
  ],
  "http://10.10.0.97:5050/imx/run": [
    "run(self, plate_id: str, hts_file: str)"
  ]
}
dan@NUC-robotlab:~$ curl 10.10.0.97:5050/imx/online
{
  "value": "20864,OK,"
}
```

## Directory listing endpoint

There is a directory listing endpoint, `dir_list`.
The first use of this was to to return information about BioTek LHC files that are grandchildren of the protocols root.
Later it was also used to list ImageXpress HTS files.
The result has looked like this:

```
dan@NUC-robotlab:~$ curl -s 10.10.0.56:5050/dir_list | grep 'automation_v4.0..2' -B1 -A3
    {
      "path": "automation_v4.0/2.0_D_SB_PRIME_Mito.LHC",
      "modified": "2022-01-18 14:01:34",
    },
    {
      "path": "automation_v4.0/2.1_D_SB_30ul_Mito.LHC",
      "modified": "2022-01-18 14:06:01",
    },
```

They are under the `"value"` key of the returned object:

```
dan@NUC-robotlab:~$ curl -s 10.10.0.56:5050/dir_list | grep '"value"' -A15
  "value": [
    {
      "path": "automation/0_W_D_PRIME.LHC",
      "modified": "2021-05-31 14:02:48",
    },
    {
      "path": "automation/1_D_P1_30ul_mito.LHC",
      "modified": "2021-05-06 10:35:57",
    },
    {
      "path": "automation/1_D_P1_PRIME.LHC",
      "modified": "2021-05-31 13:59:10",
    },
```

## Barcode scanner

Install drivers from https://support.honeywellaidc.com/s/article/How-to-get-the-scanner-to-communicate-via-virtual-COM-port-USB-serial-driver
A copy of these files are put on the nfs under `/share/data/manuals_and_software/honeywell-barcode-scanner-documentation`.

Set barcode scanner to USB Serial Emulation Mode by showing it the barcode 316460.

By default reads from COM3 and assumes barcodes separated by \r (seems to be the default anyway.)

## Configure BioTek software

Make sure that this option is checked in each protocol:

<img src=images/lhc-ports.jpg>

This can be found by going to Tools > Preferences in LHC. If the other option
is checked, the program may have difficulty switching between instruments.
The error message you would get is:

> Test Communications error. Error code: 6061 Port is no longer available.

## BlueWash

Communication should look like this:

```
dan@devserver:~$ curl windows-nuc:5050/blue/get_info
{
  "value": [
    "Err=00",
    "writing copyprog data please wait ...",
    "Err=00",
    "Err=00",
    "57724-012",
    "BW_1.51",
    "inet Adresse:192.168.1.192  Bcast:192.168.1.255  Maske:255.255.255.0",
    "Err=21"
  ]
}
dan@devserver:~$ curl windows-nuc:5050/blue/init_all
{
  "value": [
    "Err=00",
    "Err=21"
  ]
}
dan@devserver:~$ curl windows-nuc:5050/blue/rackgetoutsensor
{
  "value": [
    "Reed sensor value out = (1)",
    "Err=00"
  ]
}
dan@devserver:~$ curl windows-nuc:5050/blue/run_cmd/getprogs
{
  "value": [
    "98 _get_info.prog",
    "97 _get_info.prog",
    "02 _silly.prog",
    "01 _cp-test.prog",
    "Err=00"
  ]
}
```
