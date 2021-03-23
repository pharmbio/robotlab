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

`scriptgenerator.py`:
  generates new scripts to `generated/`
  with `--generate-stubs` instead writes stub programs for manual editing

<hr/>

`urrc.py`:
  work-in-progress communication with the UR robot

`utils.py`:
  utility file including ergonomic dict and pretty printing

