# robot remote control

Work in progress. This is the version before changing from
throughput to precise scheduling.

optional dev dependency: mypy

`notes.md`:
  most of the things I have learned working on this

`secrets-template.sh`:
  fill this in with the missing pieces and then source
  its env vars

`copyscripts.sh`:
  copy the scripts made on the teach pendant to `scripts/`

`scriptparser.py`:
  parses the scripts made on the teach pendant
  resolves locations in generated scripts

`scriptgenerator.py`:
  generates new scripts to `generated/`
  with `--generate-stubs` instead writes stub programs for manual editing

`moves.py`:
  keeps track of the "world" configuration and the moves the robots may do
  given a configuration and the effect it has upon it

`robots.py`:
  the actual commands to communicate with the robots: the UR robot arm,
  the washer, the dispenser and the incubator

`protocol.py`:
  the steps in the cell painting protocol and the initial world

`execute.py`:
  does a bfs on the world to make all plates proceed in their protocols
  as far as possible

<hr/>

`urrc.py`:
  example communication with the UR robot

`utils.py`:
  utility file for pretty printing

