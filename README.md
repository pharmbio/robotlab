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

### Liquid handling robots

Possible ways the dispenser could fail:
* no liquid in bottle (only washer has a sensor for this, dispenser will just not dispense anything if liquids run out)
* plate is not correctly inserted (tilted)
    * get stuck when moving plate
    * liquids are dispensed in wrong row/column
* some tips have changed direction, clogged or having droplets
* bacterial/other types of contamination
* liquid does not run away properly and will overflood (vacuum of tube getting to waste)
* liquids runs back in tubing if standing idle for longer than 20 minutes:
    * for cheap solutions (e.g. PFA, TritonX100 and mitotracker: prime)
    * for expensive solutions (stains coctail: pump back (purge) the liquid and prime again)
* liquids need to be primed. Each cassette has a different dead volume and might need different priming protocol.
* wrong waste bottle is connected --> PFA needs to be disposed in  appropiate container”
* plate dropped down blocking the moving parts
* waste bottle is full (liquids will not run off and overflood)
* liquids (e..g stains) stay too long in tubing
* cassettes remain attached which will damage the plastic of the tubing --> remove cassettes after running experiment
* plate is put wrong way around (unlikely with robot though)

Possible ways the washer could fail:
* no liquid in bottle (washer has a sensor for this and will throw an error)
* plate is not correctly inserted
    * get stuck when moving plate
* Z-offset is set wrong for plate (washed off cells or crashes into plate)
* Wrong bottle is selected and wrong liquid is dispensed
* waste bottle is full
* tips are clogged (commonly happens, need to be cleaned by pinching with a needle each of the pins)
