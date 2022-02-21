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

The output should look like:

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

## Directory listing endpoint

There is a directory listing endpoint, `dir_list`, which returns the information
about LHC files that are grandchildren of the protocols root. The information
is path, last modified date and sha256 hexdigest:

```
dan@NUC-robotlab:~$ curl -s 10.10.0.56:5050/dir_list | grep 'automation_v4.0..2' -B1 -A3
    {
      "path": "automation_v4.0\\2.0_D_SB_PRIME_Mito.LHC",
      "modified": "2022-01-18 14:01:34",
      "sha256": "bbf0db9aa30de9ec7b9a8d9e102a3eca7051b7605e108feb01c315bcee734de0"
    },
    {
      "path": "automation_v4.0\\2.1_D_SB_30ul_Mito.LHC",
      "modified": "2022-01-18 14:06:01",
      "sha256": "1959451ea7477e170311281ac0981c4eff8d628897dff16cf31d1e8c1b361ca1"
    },
```

They are under the `"value"` key of the returned object:

```
dan@NUC-robotlab:~$ curl -s 10.10.0.56:5050/dir_list | grep '"value"' -A15
  "value": [
    {
      "path": "automation\\0_W_D_PRIME.LHC",
      "modified": "2021-05-31 14:02:48",
      "sha256": "84fbff41b146d44488d9afe95145f20343d716dd81a6b17c843dedc18f199d55"
    },
    {
      "path": "automation\\1_D_P1_30ul_mito.LHC",
      "modified": "2021-05-06 10:35:57",
      "sha256": "40c7098eb73e6590d017baafbabf12dfe37e6b0711b59eb2125a60cd36f8bdfd"
    },
    {
      "path": "automation\\1_D_P1_PRIME.LHC",
      "modified": "2021-05-31 13:59:10",
      "sha256": "6ebc011245938a2723ad343c71140481e46d5bb098a7afa714abf5d8b4c2e20b"
    },
```

## Configure BioTek software

Make sure that this option is checked in each protocol:

<img src=images/lhc-ports.jpg>

This can be found by going to Tools > Preferences in LHC. If the other option
is checked, the program may have difficulty switching between instruments.
The error message you would get is:

> Test Communications error. Error code: 6061 Port is no longer available.

