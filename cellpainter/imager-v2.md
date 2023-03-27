# robot-imager v2

## Todo

merge movelists:
- need some way to specify which of the movelists we want:

    expressions:
        MoveLists.PF[...]
        MoveLists.UR[...]

    directories:
        movelists-ur/...
        movelists-pf/...

    def to_ur_cmd(self) -> str: ...
    def to_pf_cmd(self) -> str: ...

merge moves_gui

port scheduler_gui:
- load-fridge (small protocol, --num-plates)
- image-from-fridge (textarea input)
    project,barcode,base_name,hts_file
    protac35,(384)P000314,protac35-v1-FA-P000314-U2OS-24h-P1-L1,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
    protac35,(384)P000317,protac35-v1-FA-P000317-U2OS-24h-P2-L2,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
  but with squid confs
  + thaw hours
- fridge unload, not sure how to do this
  - fridge unload by project (?) gives you up to 9 plates from the project, in lexicographic order
- system
  - test-comm
  - robotarm freedrive start stop
  - robotarm reset and activate
  - fridge reset and activate

slack Patrick:
- directory for config files
- what needs to be known about laser auto focus and the conf files

## Idea

Idea: crash-only software like the cellpainter system.
Use "start from stage" to recover from crashes.  For imaging, the stages
will be the plates in imaging order.  The Squid and the Nikon can run
simultaneously but they have to acquire the robotarm lock before they can
move it.  This way they can both run interleaved. The contention around the
arm is very low since the ratio of moving and resting is very low.

Locks:
- Arm&Fridge lock:
    without the arm lock the arm does not move
    the robots programs will also need the arm lock for the fridge
    a human operator can take the arm lock to be sure noone will work with the fridge or arm
    - kept in SQLite db on operating computer

Call "EnsureReady" on Squid & Nikon before we move there and crash if not possible:
- before moving plate away from H11: check that Squid is OK to use
- before moving plate away from H10: check that Nikon is OK to use

H12: working area
H11: squid working area
H10: nikon working area
H1-H9: loading slots

- Fridge contents:
    - kept in SQLite db on GBG computer

Persistent state:
- Arm lock.
  Should this include the fridge? Probably, but not necessarily.  But we
  might just as well, then any manual fiddlings with the fridge has to wait
  for the arm+fridge to settle.  After a failure the human operator releases
  the arm lock when everything is in order again. This way new and pending
  events can proceed.

- Fridge contents.
  If we allow arbitrary modifications to the frige contents while a protocol
  is running we must have fridge eject and insert to be able to dynamically
  look up fridge contents.

- Locks for squid and nikon?
  For next version when the system is more used to prevent mistakes.
  With a microscope lock you can also interleave human and robotarm use
  of the arm, just request the lock and when the current work is finished
  (<6h) the human can proceed, do what it needs and release the lock again
  and the protocol continues.

UI:
Example states for locks:
- `Robotarm locked, controlled by running squid-acquire process 123456@robotlab-NUC (25 minutes ago)`
- `Robotarm locked, controlled by *dead* nikon-acquire process 123456@robotlab-NUC (25 minutes ago)`
- `Robotarm locked, controlled by operator PG (25 minutes ago)`
- `Robotarm free (since 45 minutes ago)`
Example buttons for locks:
- `Force release robotarm lock`
- `Force take robotarm lock`

Commands:
```python
Command:
def gui_boring(self) -> bool: ...
def is_physical(self) -> bool: ...
def is_compound(self) -> bool: ...
    # fork, seq, meta (lock?) ...
    # maybe just add Lock to cellpainter/commands.py

def is_noop(self) -> bool: ...
def required_resource(self) -> str | None
def effect(self) -> Effect | None

def optimize_forks(self) -> Command: ...
```
