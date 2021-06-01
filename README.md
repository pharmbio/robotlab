# robot remote control

dependencies: python 3.9, flask, pandas, scipy

optional dev dependencies: pyright, entr

rewrite in progress

The command line interface, `cli.py`, accepts the following configurations:

config name   | timers       | disp & wash   | incu         | robotarm
---           | ---          | ---           | ---          | ---
live          | wall         | execute       | execute      | execute
test-all      | fast-forward | execute-short | execute      | execute
test-arm-incu | fast-forward | instant noop  | execute      | execute
simulator     | fast-forward | instant noop  | instant noop | execute-no-gripper
dry-run       | instant noop | instant noop  | instant noop | instant noop

| filename            | description
| ---                 | ---
|                     | _a graphical user interface_
| gui.py              | teach the robotarm moves
|                     | _a command line interface_
| cli.py              | make the robots in the lab do things!
|                     | _notes_
| notes.md            | things I have learned working on this
| robocom.sh          | notes that can be run
|                     | _nice robotarm move representations_
| moves.py            | robotarm positions in mm XYZ and degrees RPY
| robotarm.py         | send moves to the robotarm and its gripper
|                     | _the other lab robots_
| robots.py           | uniform control over the washer, dispenser, incubator and the robotarm
| protocol.py         | cell painting protocol
| protocol_vis.py     | visualize timings of the cell painting protocol
| analyze_log.py      | timings statistics for a cell painting log
|                     | _communication with the robotlab network_
| secrets-template.sh | fill this in with the missing pieces and then source its env vars
|                     | _working with programs made as urscripts on the teach pendant_
| scriptparser.py     | parses the scripts and resolves locations in UR scripts
| scriptgenerator.py  | converts resolved UR scripts to the nice representations
| copyscripts.sh      | copy the scripts made on the teach pendant to `scripts/`
|                     | _utils_
| utils.py            | pretty printing and other small utils
| viable.py           | a viable alternative to front-end programming
|                     |
