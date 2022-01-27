# imx-pharmbio-automation

Control of the PreciseFlex (PF) robotarm and the MolDev ImageXpress (IMX) microscope.

We use the same kind of cliwrapper as for the bioteks to wrap both the PF and the IMX.

A scheduler repeatedly talks to the PF and the IMX to keep them busy.

A human operator can add entries to the scheduler.

<img src=overview.svg/>

### IP numbers

ip           | computer
---          | ---
`10.10.0.99` | IMX Windows computer
`10.10.0.98` | PreciseFlex robotarm
`10.10.0.97` | GBG Windows computer (to be disconnected)

### PreciseFlex notes

The webpage with documentation is at http://preciseautomation.com/ but behind a password,
so I put a copy on the nfs under `/share/data/manuals_and_software/preciseflex`.

The robotarm can be communicated with on telnet. Install rlwrap and netcat and run:

```sh
rlwrap nc 10.10.0.98 23
```

The password is `Help` (the default). The supported commands are documented under
_Controller Software/Software Reference/Console Command Summary_.

The robotarm has an ftp server. It can be mounted using curlftpfs:

```sh
mkdir -p flash
curlftpfs 10.10.0.98 flash
```

The robotarm has a web server for configuring it. You can forward it to localhost:1280 with:

```sh
ssh -N -L 1280:10.10.0.98:80 robotlab-ubuntu
```

The robotarm IP can be changed there, see _Control Panels/Communication/Network_.
There is also a virtual pendant.

The robotarm programming language is a dialect of VisualBasic.
It is called _Guidance Programming Language_ (GDS).
We use a TCP server written in GDS by PreciseAutomation called Tcp_cmd_server,
or TCS for short, with some small modifications to control the arm.
Using the telnet method is too brittle.

TCS is at port 10000 for querying and 10100 for motion related commands.
