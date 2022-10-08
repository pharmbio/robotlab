from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import *
import time
import traceback as tb

from . import commands as cmds
from .commands import Command

from .env import Env

from pbutils.mixins import ReplaceMixin, DBMixin, DB, Meta
import pbutils

@dataclass(frozen=True)
class FridgeOccupant(ReplaceMixin):
    project: str = ""
    barcode: str = ""

@dataclass(frozen=True)
class FridgeSlot(DBMixin):
    loc: str = ""
    occupant: FridgeOccupant | None = None
    id: int = -1
    __meta__: ClassVar = Meta(
        log=True,
        views={
            'project': 'value ->> "occupant.project"',
            'barcode': 'value ->> "occupant.barcode"',
        },
    )

@dataclass(frozen=True)
class Checkpoint(DBMixin):
    name: str = ""
    t: datetime = field(default_factory=datetime.now)
    id: int = -1
    __meta__: ClassVar = Meta(
        views={
            't': 'value ->> "t.value"',
        },
    )

@dataclass(frozen=True)
class QueueItem(DBMixin):
    cmd: Command = field(default_factory=cmds.Noop)
    started: datetime | None = None
    finished: datetime | None = None
    error: str | None = None
    pos: int = -1
    id: int = -1
    __meta__: ClassVar = Meta(
        log=True,
        views={
            'type': 'value ->> "cmd.type"',
            'started': 'value ->> "started.value"',
            'finished': 'value ->> "finished.value"',
        },
    )

pbutils.serializer.register(globals())

FRIDGE_LOCS = [
    f'{slot+1}x{level+1}'
    for slot in range(8)
    for level in range(17)
]

def ensure_fridge(db: DB):
    with db.transaction:
        FridgeSlots = db.get(FridgeSlot)
        for loc in FRIDGE_LOCS:
            if not FridgeSlots.where(FridgeSlot.loc == loc):
                FridgeSlot(loc).save(db)

from typing import *

def enqueue(env: Env, cmds: list[Command], where: Literal['first', 'last'] = 'last'):
    with env.db.transaction:
        ensure_fridge(env.db)
        if where == 'last':
            last_pos = max((q.pos for q in env.db.get(QueueItem)), default=0)
            for pos, cmd in enumerate(cmds, start=last_pos + 1):
                assert pos > last_pos
                QueueItem(cmd=cmd, pos=pos).save(env.db)
        elif where == 'first':
            first_pos = min((q.pos for q in env.db.get(QueueItem)), default=0)
            print(f'{first_pos=}')
            for pos, cmd in enumerate(cmds, start=first_pos - len(cmds)):
                assert pos < first_pos
                print(QueueItem(cmd=cmd, pos=pos).save(env.db))
        else:
            raise ValueError(f'{where=} not valid')


def execute(env: Env, keep_going: bool):
    while True:
        while True:
            todo = env.db.get(QueueItem).where(QueueItem.finished == None).order(QueueItem.pos).limit(1).list()
            if not todo:
                print('nothing to do')
                break
            else:
                item = todo[0]
                print('item:', item)
                if item.started and item.error:
                    print(item.error)
                    print('the top of the queue has errored')
                    break
                if not item.started:
                    item = item.replace(started=datetime.now()).save(env.db)
                else:
                    assert isinstance(item.cmd, (cmds.WaitForIMX, cmds.Pause, cmds.WaitForCheckpoint))
                try:
                    res = execute_one(item.cmd, env)
                    if env.is_sim and not isinstance(item.cmd, cmds.CheckpointCmd):
                        time.sleep(1)
                except:
                    item = item.replace(error=tb.format_exc()).save(env.db)
                else:
                    if res == 'wait':
                        time.sleep(1)
                    else:
                        item = item.replace(finished=datetime.now()).save(env.db)
                print('item:', item)
        if keep_going:
            time.sleep(3)
            pass
        else:
            return

def execute_one(cmd: Command, env: Env) -> None | Literal['wait']:
    FridgeSlots = env.db.get(FridgeSlot)
    Checkpoints = env.db.get(Checkpoint)
    pbutils.pr(cmd)
    match cmd:
        case cmds.RobotarmCmd():
            with env.get_robotarm() as arm:
                before_each = None
                if cmd.keep_imx_open:
                    before_each = lambda: (env.imx.open(sync=False) , None)[-1]
                arm.execute_movelist(cmd.program_name, before_each=before_each)

        case cmds.Acquire():
            env.imx.acquire(plate_id=cmd.plate_id, hts_file=cmd.hts_file)
        case cmds.Open():
            env.imx.open(sync=True)
        case cmds.Close():
            env.imx.close()
        case cmds.WaitForIMX():
            if not env.imx.is_ready():
                return 'wait'
        case cmds.Pause():
            return 'wait'

        case cmds.FridgePutByBarcode():
            barcode = env.barcode_reader.read_and_clear()
            assert barcode
            if cmd.check_barcode is not None:
                if env.is_sim:
                    barcode = cmd.check_barcode
                # check that the plate has the barcode we thought we were holding
                assert barcode == cmd.check_barcode, f'Expected {cmd.check_barcode} but read {barcode}'
            slot, *_ = FridgeSlots.where(FridgeSlot.occupant == None)
            next_cmd = cmds.FridgePut(loc=slot.loc, project=cmd.project, barcode=barcode)
            return execute_one(next_cmd, env)

        case cmds.FridgePut():
            [slot] = FridgeSlots.where(FridgeSlot.loc == cmd.loc)
            assert slot.occupant is None
            env.fridge.put(cmd.loc)
            occupant = FridgeOccupant(project=cmd.project, barcode=cmd.barcode)
            slot.replace(occupant=occupant).save(env.db)

        case cmds.FridgeGetByBarcode():
            occupant = FridgeOccupant(project=cmd.project, barcode=cmd.barcode)
            [slot] = FridgeSlots.where(FridgeSlot.occupant == occupant)
            return execute_one(cmds.FridgeGet(slot.loc, check_barcode=True), env)

        case cmds.FridgeGet():
            [slot] = FridgeSlots.where(FridgeSlot.loc == cmd.loc)
            assert slot.occupant is not None
            env.fridge.get(cmd.loc)
            if cmd.check_barcode and not env.is_sim:
                # check that the popped plate has the barcode we thought was in the fridge
                barcode = env.barcode_reader.read_and_clear()
                assert slot.occupant.barcode == barcode
            slot.replace(occupant=None).save(env.db)

        case cmds.FridgeAction():
            env.fridge.action(cmd.action)

        case cmds.BarcodeClear():
            env.barcode_reader.clear()

        case cmds.CheckpointCmd():
            for dup in Checkpoints.where(Checkpoint.name == cmd.name):
                dup.delete(env.db)
            Checkpoint(name=cmd.name).save(env.db)
        case cmds.WaitForCheckpoint():
            [checkpoint] = Checkpoints.where(Checkpoint.name == cmd.name)
            if datetime.now() < checkpoint.t + cmd.plus_timedelta:
                return 'wait'

        case cmds.Noop():
            pass

