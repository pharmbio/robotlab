# imx-server

Exposes the IMX microscope External Control Protocol COM port using on a
http server using python, flask and pyserial.

### Installation

```
pip install --editable .
```

### Running

```
imx-server.exe
```

### Example dialogue

```
dan@NUC-robotlab:~$ curl 10.10.0.99:5050 -d msg=1,STATUS
{
  "sent": "1,STATUS",
  "reply": "20864,OFFLINE"
}
dan@NUC-robotlab:~$ curl 10.10.0.99:5050 -d msg=1,ONLINE
{
  "sent": "1,ONLINE",
  "reply": "20864,OK,"
}
dan@NUC-robotlab:~$ curl 10.10.0.99:5050 -d msg=1,STATUS
{
  "sent": "1,STATUS",
  "reply": "20864,READY,UNKNOWN"
}
dan@NUC-robotlab:~$ curl 10.10.0.99:5050 -d msg=1,VERSION
{
  "sent": "1,VERSION",
  "reply": "20864,1.1"
}
```

Read the pdf for more information about the supported messages.
