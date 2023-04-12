from __future__ import annotations
from dataclasses import *
from typing import *

import socket
import contextlib
import sqlite3

from .machine import Machine
from .sqlitecell import SqliteCell

@dataclass(frozen=True)
class STX(Machine):
    id: str = "STX"
    host: str = "localhost"
    port: int = 3333
    mode: Literal['noop', 'execute'] = 'execute'

    def call(self, command_name: str, *args: Union[str, float, int]):
        '''
        Call any STX command.

        Example: curl -s 10.10.0.56:5050/incu/call/STX2ReadActualClimate
        '''
        args = (self.id, *args)
        csv_args = ",".join(str(arg) for arg in args)
        return self._send(f'{command_name}({csv_args})')

    def _send(self, line: str) -> str:
        with self.atomic():
            msg = line.strip().encode('ascii') + b'\r'
            self.log(f'stx.write({msg!r})')

            if self.mode == 'execute':
                with contextlib.closing(socket.create_connection((self.host, self.port))) as sock:
                    sock.sendall(msg)
                    reply_bytes = sock.recv(8192) # replies are only a few bytes
            elif self.mode == 'noop':
                reply_bytes = b'1\r\n'
            else:
                raise ValueError(f'Invalid {self.mode=!r}')

            self.log(f'stx.read() = {reply_bytes!r}')
            reply = reply_bytes.decode('ascii').strip()
            return reply

    def _parse_pos(self, pos: str) -> Tuple[int, int]:
        if pos[0] == "L":
            slot = 1
        elif pos[0] == "R":
            slot = 2
        else:
            casette_str, x, level_str = pos.partition('x')
            if x != 'x':
                raise ValueError('pos should start with L or R indicate cassette 1 or 2, or <CASETTE>x<LEVEL>')
            slot = int(casette_str)
            level = int(level_str)
            return slot, level
        # pos[1:] should be level, 1-indexed
        level = int(pos[1:])
        return slot, level

    def _parse_climate(self, response: str) -> Dict[str, float]:
        '''
        temp:  temperature in °C.
        humid: relative humidity in percent.
        co2:   CO₂ concentration in percent.
        n2:    N₂ concentration in percent.
        '''
        temp, humid, co2, n2 = map(float, response.split(";"))
        climate = {
            "temp": temp,
            "humid": humid,
            "co2": co2,
            "n2": n2,
        }
        return climate

    def get_status(self) -> dict[str, bool]:
        response = self.call("STX2GetSysStatus")
        response = int(response)
        assert response != -1
        bits = {
            'System Ready':          0,
            'Plate Ready':           1,
            'System Initialized':    2,
            'XferStn status change': 3,
            'Gate closed':           4,
            'User door':             5,
            'Warning':               6,
            'Error':                 7,
        }
        value = {
            name: bool(response & (1 << bit))
            for name, bit in bits.items()
        }
        return value

    def get_climate(self):
        '''
        temp:  current temperature in °C.
        humid: current relative humidity in percent.
        co2:   current CO2 concentration in percent.
        n2:    current N2 concentration in percent.
        '''
        response = self.call("STX2ReadActualClimate")
        return self._parse_climate(response)

    def get_target_climate(self) -> dict[str, float]:
        '''
        temp:  target temperature in °C.
        humid: target relative humidity in percent.
        co2:   target CO2 concentration in percent.
        n2:    target N2 concentration in percent.
        '''
        response = self.call("STX2ReadSetClimate")
        return self._parse_climate(response)

    def set_target_climate(self, temp: str, humid: str, co2: str, n2: str):
        '''
        temp:  target temperature in °C.
        humid: target relative humidity in percent.
        co2:   target CO2 concentration in percent.
        n2:    target N2 concentration in percent.

        Maybe driver wants co2 and n2 in the opposite order here...
        '''
        self.call("STX2WriteSetClimate", temp, humid, co2, n2)

    def reset_and_activate(self):
        self.call("STX2Reset")
        response = self.call("STX2Activate")
        assert response == "1" or response == "1;1"

    def get(self, pos: str):
        """
        Gets the plate from a position, L<LEVEL> or R<LEVEL> indicate cassette 1 or 2, or <CASETTE>x<LEVEL>.
        """
        slot, level = self._parse_pos(pos)
        self._move(src_pos='Hotel', src_slot=slot, src_level=level)

    def put(self, pos: str):
        """
        Puts the plate to a position, L<LEVEL> or R<LEVEL> indicate cassette 1 or 2, or <CASETTE>x<LEVEL>.
        """
        slot, level = self._parse_pos(pos)
        self._move(trg_pos='Hotel', trg_slot=slot, trg_level=level)

    def _move(
        self,
        src_pos:   str = 'TransferStation',
        src_slot:  int = 0,
        src_level: int = 0,
        trg_pos:   str = 'TransferStation',
        trg_slot:  int = 0,
        trg_level: int = 0,
    ):
        '''
        SrcID,        TrgId:    device identifier
        SrcPos,       TrgPos:   1=TransferStation, 2=Slot-Level Position
        SrcSlot,      TrgSlot:  plate slot (cassette) position
        SrcLevel,     TrgLevel: plate level position
        TransSrcSlot, TransTrgSlot: (not relevant for us)
        SrcPlType,    TrgPlType: plate type 0=MTP, 1=DWP, 3=P28 (not sure if matters)
        '''
        args = {
            # SrcID: self.id (implicit, added by call),
            'SrcPos':       1 if src_pos == 'TransferStation' else 2,
            'SrcSlot':      src_slot,
            'SrcLevel':     src_level,
            'TransSrcSlot': 1,
            'SrcPlType':    1,
            'TrgID':        self.id,
            'TrgPos':       1 if trg_pos == 'TransferStation' else 2,
            'TrgSlot':      trg_slot,
            'TrgLevel':     trg_level,
            'TransTrgSlot': 1,
            'TrgPlType':    1,
        }
        assert self.call('STX2ServiceMovePlate', *args.values()) == "1"

class FridgeSlot(TypedDict):
    plate: str
    project: str

empty_slot = FridgeSlot(plate='', project='')

FridgeSlots = dict[str, FridgeSlot]

@dataclass(frozen=True)
class FridgeDB(SqliteCell[FridgeSlots]):
    table: str = 'Fridge'
    key: str = 'fridge'
    default: FridgeSlots = field(default_factory=dict)

    def normalize(self, value: FridgeSlots):
        return {
            loc: FridgeSlot(**slot)
            for loc, slot in sorted(value.items())
        }

    def update_loc(self, loc: str, slot: FridgeSlot):
        slots = self.read()
        slots[loc] = slot
        self.write(slots)

    __setitem__ = update_loc

    def get_by_loc(self, loc: str) -> FridgeSlot | None:
        return self.read().get(loc)

    __getitem__ = get_by_loc

    def get_by_plate_project(self, plate: str, project: str) -> tuple[str, FridgeSlot] | None:
        for loc, slot in self.read().items():
            if slot['plate'] == plate and slot['project'] == project:
                return loc, slot

    def get_empty(self) -> tuple[str, FridgeSlot] | None:
        return self.get_by_plate_project('', '')

@dataclass(frozen=True)
class Fridge(STX):
    fridge_db: str = 'fridge.db'

    @contextlib.contextmanager
    def _get_db(self) -> Iterator[FridgeDB]:
        con = sqlite3.connect(self.fridge_db, isolation_level=None)
        db = FridgeDB(con)
        with db.exclusive():
            yield db
        con.close()

    def contents(self) -> FridgeSlots:
        '''
        Returns a listing of the fridge contents.
        '''
        with self._get_db() as db:
            return db.read()

    def rewrite_contents(self, current: FridgeSlots, next: FridgeSlots, bypass_db_check: bool=False) -> FridgeSlots:
        '''
        Rewrites the contents of the fridge. Succeeds iff the current argument matches the current database (unless using the bypass check argument).

        Returns the new contents.
        '''
        with self._get_db() as db:
            db_current = db.read()
            current = db.normalize(current)
            if bypass_db_check:
                pass
            elif db_current != current:
                raise ValueError(f'Current value mismatch: {db_current=} != {current=}')
            db.write(next)
            return next

    def add_capacity(self, *locs: str):
        '''
        Makes sure the locations are registered in the fridge database,
        adding a new entry to an empty slot if necessary.
        '''
        for loc in locs:
            a, x, b = loc.partition('x')
            assert a.isdigit()
            assert x == 'x'
            assert b.isdigit()
        with self._get_db() as db:
            for loc in locs:
                if db.get_by_loc(loc) is None:
                    db[loc] = empty_slot

    def insert(self, plate: str, project: str) -> tuple[str, FridgeSlot]:
        '''
        Inserts a plate on either some empty location.

        Returns info about the plate and the new location, or raises an error if it was not possible to complete the action.
        '''
        assert plate and project
        with self.atomic():
            with self._get_db() as db:
                loc_slot = db.get_empty()
                if not loc_slot:
                    raise ValueError('No empty slot')
                loc, _old_slot = loc_slot

            self.put(loc)

            with self._get_db() as db:
                slot = FridgeSlot(plate=plate, project=project)
                db[loc] = slot
                return loc, slot

    def insert_by_loc(self, loc: str, plate: str, project: str) -> tuple[str, FridgeSlot]:
        '''
        Inserts a plate on a location specified as argument.

        Returns info about the plate and the new location, or raises an error if it was not possible to complete the action.
        '''
        with self.atomic():
            with self._get_db() as db:
                old_slot = db.get_by_loc(loc)
                if not old_slot:
                    raise ValueError(f'No slot with {loc=}')
                if old_slot['plate'] or old_slot['project']:
                    raise ValueError(f'Target slot not empty {old_slot=}')

            self.put(loc)

            with self._get_db() as db:
                slot = FridgeSlot(plate=plate, project=project)
                db[loc] = slot
                return loc, slot


    def eject(self, plate: str, project: str) -> tuple[str, FridgeSlot]:
        '''
        Ejects a plate given a plate and project.

        Returns info about the plate and the old location, or raises an error if it was not possible to complete the action.
        '''
        with self.atomic():
            with self._get_db() as db:
                loc_slot = db.get_by_plate_project(plate, project)
                if not loc_slot:
                    raise ValueError(f'No slot with {plate=} and {project=}')
                loc, slot = loc_slot
            return self._eject(loc, slot)

    def eject_by_loc(self, loc: str) -> tuple[str, FridgeSlot]:
        '''
        Ejects a plate given a location. The database will be consulted if the location contains a plate (unless using the bypass check argument).

        To eject without checking the DB use the method name get.

        Returns info about the plate and the old location, or raises an error if it was not possible to complete the action.
        '''
        with self.atomic():
            with self._get_db() as db:
                slot = db.get_by_loc(loc)
                if not slot:
                    raise ValueError(f'No slot with {loc=}')
                if not slot['plate']:
                    raise ValueError(f'Target slot empty {slot=}')
            return self._eject(loc, slot)

    def _eject(self, loc: str, slot: FridgeSlot) -> tuple[str, FridgeSlot]:
        with self.atomic():
            self.get(loc)
            with self._get_db() as db:
                empty_slot = FridgeSlot(plate='', project='')
                db[loc] = empty_slot
                return loc, slot

@contextlib.contextmanager
def get_test_fridge():
    import tempfile
    from flask import Flask
    from pathlib import Path
    app = Flask(__name__) # need a test context for .log to work with Machines
    with app.test_request_context():
        with tempfile.TemporaryDirectory(prefix='fridge-') as tmpdir:
            fridge_db=str(Path(tmpdir)/'fridge.db')
            yield Fridge(fridge_db=fridge_db, mode='noop')

def test_fridge():
    import pytest
    with get_test_fridge() as fridge:
        fridge.add_capacity('1x1', '1x2')
        assert fridge.contents() == {'1x1': empty_slot, '1x2': empty_slot}

        slot1 = FridgeSlot(plate=(plate1 := 'PB1701'), project=(project1 := 'ambi-40k'))
        slot2 = FridgeSlot(plate=(plate2 := 'PB1703'), project=(project2 := 'ambi-40k'))

        loc, slot = fridge.insert(plate1, project1)
        assert loc == '1x1'
        assert slot == slot1
        assert fridge.contents() == {'1x1': slot1, '1x2': empty_slot}

        loc, slot = fridge.insert(plate2, project2)
        assert loc == '1x2'
        assert slot == slot2
        assert fridge.contents() == {'1x1': slot1, '1x2': slot2}

        with pytest.raises(ValueError):
            # full
            loc, slot = fridge.insert('PB1705', 'ambi-40k')

        loc, slot = fridge.eject(plate1, project1)
        assert loc == '1x1'
        assert slot == slot1
        assert fridge.contents() == {'1x1': empty_slot, '1x2': slot2}

        loc, slot = fridge.eject_by_loc('1x2')
        assert loc == '1x2'
        assert slot == slot2
        assert fridge.contents() == {'1x1': empty_slot, '1x2': empty_slot}

        with pytest.raises(ValueError):
            # loc empty
            loc, slot = fridge.eject_by_loc('1x2')

        with pytest.raises(ValueError):
            # no such loc
            loc, slot = fridge.eject_by_loc('41x2')

        with pytest.raises(ValueError):
            # no such plate
            loc, slot = fridge.eject(plate1, project1)

        loc, slot = fridge.insert_by_loc('1x1', plate1, project1)
        assert loc == '1x1'
        assert slot == slot1
        assert fridge.contents() == {'1x1': slot1, '1x2': empty_slot}

        with pytest.raises(ValueError):
            # loc taken
            loc, slot = fridge.insert_by_loc('1x1', plate1, project1)

        with pytest.raises(ValueError):
            # no such loc
            loc, slot = fridge.insert_by_loc('41x1', plate1, project1)

        fridge.rewrite_contents(
            current=fridge.contents(),
            next={'1x1': slot1, '1x2': slot2}
        )
        assert fridge.contents() == {'1x1': slot1, '1x2': slot2}

        with pytest.raises(ValueError):
            # wrong current
            fridge.rewrite_contents(
                current={},
                next={'1x1': slot1, '1x2': slot2}
            )
