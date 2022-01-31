# PreciseFlex control

...

## Tcp_cmd_server, modified

These commands are added:

```
' Cmd_WhereJson -- Gets the robot positions in json
' Cmd_MoveJ_NoGripper -- Move to a location defined by angles, excluding the gripper joint (5)
' Cmd_MoveGripper -- Move the gripper joint (5)
' Cmd_MoveJ_Rel -- Move joints relative
' Cmd_MoveC_Rel -- Move cartesian relative
```

Try them on port 10.10.0.98:10100, but first put verbose, power on, attach and home:

```sh
rlwrap nc 10.10.0.98 10100
```
```
mode 1
hp 1
attach 1
home
MoveJ_Rel 1 0 0 0 0 -10
MoveC_Rel 1 10 0 0 0 0 0
```

See the documentation pdf for more info.

## Flashing the PreciseFlex

We flash the modified version of the ./Tcp_cmd_server/ to the robot arm on the telnet port 23.
Because this port is so brittle we keep one connection open by following the tail of a fifo.

Run `python flash.py` and follow the instructions:

```sh
dan@NUC-robotlab:~/imx-pharmbio-automation/pf_repl$ python flash.py

        Using pf23.fifo as fifo. If the fifo is not connected then run:

            tail -f pf23.fifo | nc 10.10.0.98 23

        When done you can send quit and then close nc:

            >>pf23.fifo echo quit

        The rest of this program outputs commands corresponding to its communication on the fifo.

>>pf23.fifo echo Help # this is the default password
```

Concurrently, we run nc in another terminal as per the instructions:

```sh
dan@NUC-robotlab:~/imx-pharmbio-automation/pf_repl$ tail -f pf23.fifo | nc 10.10.0.98 23



Welcome to the GPL Console

Password:

GPL: stop -all
GPL: unload -all
GPL: execute File.CreateDirectory("/flash/projects/Tcp_cmd_server")
*Interlocked for read*
GPL: load /flash/projects/Tcp_cmd_server -compile
01-31-2022 04:07:40: project Tcp_cmd_server, begin compiler pass 1
01-31-2022 04:07:40: project Tcp_cmd_server, begin compiler pass 2
01-31-2022 04:07:40: project Tcp_cmd_server, begin compiler pass 3
Compile successful
GPL: execute StartMain()
GPL:
```

The first terminal has now finished with:
```sh
>>pf23.fifo echo 'stop -all'
>>pf23.fifo echo 'unload -all'
>>pf23.fifo echo 'execute File.CreateDirectory("/flash/projects/Tcp_cmd_server")'
# ftp_store: Cmd.gpl
# ftp_store: Tcs.gpo
# ftp_store: Functions.gpl
# ftp_store: Load_save.gpl
# ftp_store: Class_StringList.gpl
# ftp_store: Class_station.gpl
# ftp_store: Globals.gpl
# ftp_store: Class_command.gpl
# ftp_store: Main.gpl
# ftp_store: Class_vector3.gpl
# ftp_store: Pharmbio.gpl
# ftp_store: Class_gpofile.gpl
# ftp_store: Project.gpr
# ftp_store: Startup.gpl
# ftp_store: Custom.gpl
>>pf23.fifo echo 'load /flash/projects/Tcp_cmd_server -compile'
>>pf23.fifo echo 'execute StartMain()'
```
