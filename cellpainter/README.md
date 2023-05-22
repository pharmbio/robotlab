# robot-cellpainter

This directory contains the code for the robotlab protocols, and their scheduler and executor.
The directory contains the code for both the cell painter system and the imager system.

dependencies: python 3.10

optional dev dependencies: pyright, entr

## Standard operating procedure

See [sop.md](./sop.md).

## Installation

```
pip install --editable .
```

## Test

```
pytest
```

and

```
./cli-tests.sh
```

or, for example:

```
cellpainter --cell-paint 6,6 --simulate
```

Github actions is set up, check .github/workflows/test.yml.
Run this locally using [`act`](https://github.com/nektos/act).

## 8-bot gripper for UR

We use the rs485-1.0.urcap from the UR ROS driver project.
This driver exposes the RS485-communication on port 54321.

https://github.com/UniversalRobots/Universal_Robots_ROS_Driver/tree/master/ur_robot_driver/resources
https://github.com/UniversalRobots/Universal_Robots_ROS_Driver/blob/master/ur_robot_driver/doc/setup_tool_communication.md

These urcap file are also the nfs under `/share/data/manuals_and_software/8bot-gripper`.

```sh
dan@NUC-robotlab:~$ rlwrap nc 10.10.0.112 54321
help

## HELP ##

start sign: ~ (0x7E)
stop sign: lf (0x0a)

ping [float]: answer pong and mirror value
help
save: store parameters permanently
s_force [float]: set force in mA
s_l_op [float]: set open width in mm
s_l_cl [float]
s_l_al [float]
s_p_op [float]
s_p_cl [float]
s_p_al [float]
g_pos: get current position
home: home gripper
m_close: close gripper with set force
m_l_op: move to landscape open
m_p_op: move to portrait open
m_pos [float]: move to position
stop: disable gripper motor
```
