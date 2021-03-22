# robot remote control

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
  can be used to generate a stub `scriptgenerator.py`

`scriptgenerator.py`:
  generates new scripts to `generated/`

<hr/>

`urrc.py`:
  work-in-progress communication with the UR robot

`show.py`:
  utility file to show python values

`protocol.py`:
  an attempt to parse the primary ur protocol. this won't be used
