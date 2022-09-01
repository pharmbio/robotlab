from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
import time
import traceback as tb

from . import commands as cmds
from .commands import Command

from .env import Env

from .utils.mixins import DBMixin, DB, Meta
from . import utils

@dataclass(frozen=True)
class FridgeSlot(DBMixin):
    loc: str = ""
    occupant: None | str = None
    id: int = -1
    __meta__: ClassVar = Meta(log=True)

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

utils.serializer.register(globals())

FRIDGE_LOCS = [
    f'{slot+1}x{level+1}'
    for slot in range(1)
    for level in range(17)
]

def ensure_fridge(db: DB):
    FridgeSlots = db.get(FridgeSlot)
    for loc in FRIDGE_LOCS:
        if not FridgeSlots.where(loc=loc):
            FridgeSlot(loc).save(db)

def enqueue(env: Env, cmds: list[Command]):
    ensure_fridge(env.db)
    last_pos = max((q.pos for q in env.db.get(QueueItem)), default=0)
    for pos, cmd in enumerate(cmds, start=last_pos + 1):
        QueueItem(cmd=cmd, pos=pos).save(env.db)

def execute(env: Env, keep_going: bool):
    while True:
        while True:
            todo = env.db.get(QueueItem).order(by='pos').limit(1).where(finished=None)
            if not todo:
                print('nothing to do')
                break
            else:
                item = todo[0]
                print('item:', item)
                if item.started and item.error:
                    print('the top of the queue has errored')
                    break
                if item.started and not item.finished:
                    print('the top of the queue is already running')
                    break
                item = item.replace(started=datetime.now()).save(env.db)
                try:
                    execute_one(item.cmd, env)
                    if env.is_sim and not isinstance(item.cmd, cmds.CheckpointCmd):
                        time.sleep(5)
                except:
                    item = item.replace(error=tb.format_exc()).save(env.db)
                else:
                    item = item.replace(finished=datetime.now()).save(env.db)
                print('item:', item)
        if keep_going:
            time.sleep(3)
        else:
            return

def execute_one(cmd: Command, env: Env) -> None:
    FridgeSlots = env.db.get(FridgeSlot)
    Checkpoints = env.db.get(Checkpoint)
    utils.pr(cmd)
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
            while not env.imx.is_ready():
                time.sleep(1)

        case cmds.FridgePutByBarcode():
            barcode = env.barcode_reader.read_and_clear()
            assert barcode
            slot, *_ = FridgeSlots.where(occupant=None)
            return execute_one(cmds.FridgePut(slot.loc, barcode), env)

        case cmds.FridgeGetByBarcode():
            [slot] = FridgeSlots.where(occupant=cmd.barcode)
            return execute_one(cmds.FridgeGet(slot.loc, check_barcode=True), env)

        case cmds.FridgePut():
            [slot] = FridgeSlots.where(loc=cmd.loc)
            assert slot.occupant is None
            env.fridge.put(cmd.loc)
            slot.replace(occupant=cmd.barcode).save(env.db)

        case cmds.FridgeGet():
            [slot] = FridgeSlots.where(loc=cmd.loc)
            assert slot.occupant is not None
            env.fridge.get(cmd.loc)
            if cmd.check_barcode and not env.is_sim:
                # check that the popped plate has the barcode we thought was in the fridge
                barcode = env.barcode_reader.read_and_clear()
                assert slot.occupant == barcode
            slot.replace(occupant=None).save(env.db)

        case cmds.FridgeAction():
            env.fridge.action(cmd.action)

        case cmds.BarcodeClear():
            env.barcode_reader.clear()

        case cmds.CheckpointCmd():
            for dup in Checkpoints.where(name=cmd.name):
                dup.delete(env.db)
            Checkpoint(name=cmd.name).save(env.db)
        case cmds.WaitForCheckpoint():
            [checkpoint] = Checkpoints.where(name=cmd.name)
            while datetime.now() < checkpoint.t + cmd.plus_timedelta:
                time.sleep(1)

        case cmds.Noop():
            pass

