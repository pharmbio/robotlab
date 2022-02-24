# imx_repl

Exposes the IMX microscope External Control Protocol COM port on stdio using pyserial.

### Installation

```
pip install --editable .
```

### Running

```
imx_repl.exe
```

### Example dialogue

```
pharmbio@NUC-robotlab:~$ curl 10.10.0.97:5050/imx --data-urlencode msg=STATUS
{
  "lines": [
    "message sent 10 bytes: b'1,STATUS\\r\\n'",
    "message reply b'20864,OFFLINE\\r\\n'",
    "success"
  ],
  "success": true,
  "value": "20864,OFFLINE"
}
pharmbio@NUC-robotlab:~$ curl 10.10.0.97:5050/imx/STATUS
{
  "lines": [
    "message sent 10 bytes: b'1,STATUS\\r\\n'",
    "message reply b'20864,OFFLINE\\r\\n'",
    "success"
  ],
  "success": true,
  "value": "20864,OFFLINE"
}
```

Some commands to run a hts file with a "barcode": a plate identifier.

```sh
./utils.sh imx-send 'run,test-barcode-1234_5678XYZ,C:\Data\specs.hts'
./utils.sh imx-send 'run,test-barcode banana 1234_5678XYZ,C:\Data\specs.hts'
./utils.sh imx-send 'run,test-barcode banana 1234_5678XYZ,C:\Data\specs - Copy.hts'
```

Open and close the microscope:

```sh
./utils.sh imx-send 'GOTO,UNLOAD'
./utils.sh imx-send 'GOTO,LOAD'
./utils.sh imx-send 'GOTO,SAMPLE'
```

You can repeatedly send `UNLOAD` to make the hatch not close. Otherwise it
will automatically close after about 1 minute:

```sh
while true; do ./utils.sh imx-send 'GOTO,UNLOAD'; done
```

Read the pdf for more information about the supported messages.
