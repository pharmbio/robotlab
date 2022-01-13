# robot remote control

dependencies: python 3.10

optional dev dependencies: pyright, entr

## installation

```
pip install --editable .
```

## test

```
cellpainter --cell-paint 6,6
```

configs:

```
--live
--dry-run
--dry-wall
--simulator
--forward
```

## network

machine        | ip
---            | ---
Ubuntu NUC     | 10.0.0.55
Windows NUC    | 10.0.0.56
UR control box | 10.0.0.112

The windows nuc runs the labrobots http endpoint on `10.10.0.56:5050`.

## file overview

| filename       | description
| ---            | ---
|                | _a command line interface_
| cli.py         | make the robots in the lab do things such as cell paint
|                | _a graphical user interface_
| gui.py         | teach the robotarm moves
|                | _notes_
| notes.md       | things I have learned working on this
| run.sh         | notes that can be run
|                | _nice robotarm move representations_
| moves.py       | robotarm positions in mm XYZ and degrees RPY
| robotarm.py    | send moves to the robotarm and its gripper
|                | _the other lab robots_
| robots.py      | uniform control over the washer, dispenser, incubator and the robotarm
| protocol.py    | cell painting protocol
|                | _utils_
| utils.py       | pretty printing and other small utils
| viable.py      | a viable alternative to front-end programming
|                |

