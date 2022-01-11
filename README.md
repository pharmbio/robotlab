# imx-pharmbio-automation

Control of the PreciseFlex robotarm and the MolDev ImageXpress (IMX) microscope.

### IP numbers

ip           | computer
---          | ---
`10.10.0.99` | IMX Windows computer
`10.10.0.98` | PreciseFlex robotarm
`10.10.0.97` | GBG Windows computer (to be disconnected)

### PreciseFlex notes

The webpage with documentation is at http://preciseautomation.com/ but under a password. A copy of it is stored on the devserver password manager.

The robot can be communicated with on telnet. Install rlwrap and netcat and run:

```sh
rlwrap nc 10.10.0.98 23
```

The password is `Help` (the default). The supported commands are documented under _Controller Software/Software Reference/Console Command Summary_.

The robot has an ftp server. It can be mounted using curlftpfs:

```sh
mkdir -p flash
curlftpfs 10.10.0.98 flash
```

The robot programming language is a dialect of VisualBasic. It is called _Guidance Programming Language_ (GDS).
We use a TCP server written in GDS by PreciseAutomation called Tcp_cmd_server,
or TCS for short, with some small modifications to control the arm.
Using the telnet method is too brittle.

TCS is at port 10000 for querying and 10100 for motion related commands.
