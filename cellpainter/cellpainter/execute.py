from __future__ import annotations
from typing import *
from dataclasses import *

import contextlib

from . import commands
from .commands import *

from .log import (
    CommandState,
    RuntimeMetadata,
    CommandWithMetadata,
)

from .runtime import RuntimeConfig, Runtime, simulate
from . import commandlib
from . import commands
from . import constraints
import pbutils
from .moves import movelists, MoveList
from . import moves
from . import bioteks
from . import bluewash
from . import incubator
from . import protocol_paths
from .estimates import estimate
from . import estimates
from datetime import datetime

from pbutils.mixins import DB, DBMixin

def execute(cmd: Command, runtime: Runtime, metadata: Metadata):
    if isinstance(cmd, PhysicalCommand) and metadata.est is None:
        metadata = metadata.merge(Metadata(est=estimate(cmd)))
    entry = CommandWithMetadata(cmd=cmd, metadata=metadata)
    match cmd:
        case Meta():
            execute(cmd.command, runtime, metadata.merge(cmd.metadata))

        case SeqCmd():
            for c in cmd.commands:
                execute(c, runtime, metadata)

        case Idle():
            secs = cmd.secs
            assert isinstance(secs, (float, int))
            entry = entry.merge(Metadata(est=round(secs, 3)))
            with runtime.timeit(entry):
                runtime.sleep(secs)

        case Checkpoint():
            runtime.checkpoint(cmd.name, entry)

        case WaitForCheckpoint():
            plus_secs = cmd.plus_secs
            assert isinstance(plus_secs, (float, int))
            t0 = runtime.wait_for_checkpoint(cmd.name)
            desired_point_in_time = t0 + plus_secs
            delay = desired_point_in_time - runtime.monotonic()
            entry = entry.merge(Metadata(est=round(delay, 3)))
            if entry.metadata.id:
                with runtime.timeit(entry):
                    runtime.sleep(delay)
            else:
                runtime.sleep(delay)

        case Duration():
            t0 = runtime.wait_for_checkpoint(cmd.name)
            runtime.timeit_end(entry, t0=t0)

        case Fork():
            thread_resource = cmd.resource
            thread_metadata = metadata.merge(Metadata(thread_resource=thread_resource))

            @runtime.spawn
            def fork():
                runtime.register_thread(f'{thread_resource} {thread_metadata.id}')
                execute(cmd.command, runtime, thread_metadata)
                runtime.thread_done()

        case RobotarmCmd():
            with runtime.timeit(entry):
                if runtime.config.ur_env.mode == 'noop':
                    if cmd.program_name not in movelists:
                        raise ValueError(f'Missing robotarm move {cmd.program_name}')
                    if metadata.sim_delay:
                        print(metadata.sim_delay)
                    runtime.sleep(estimate(cmd) + (metadata.sim_delay or 0))
                else:
                    movelist = MoveList(movelists[cmd.program_name])
                    with runtime.get_ur(include_gripper=movelist.has_gripper()) as arm:
                        arm.execute_moves(movelist, name=cmd.program_name)

        case BiotekCmd():
            with runtime.timeit(entry):
                if metadata.sim_delay:
                    runtime.sleep(metadata.sim_delay or 0)
                bioteks.execute(runtime, entry, cmd.machine, cmd.protocol_path, cmd.action)

        case BlueCmd():
            with runtime.timeit(entry):
                if metadata.sim_delay:
                    runtime.sleep(metadata.sim_delay or 0)
                bluewash.execute(runtime, entry, action=cmd.action, protocol_path=cmd.protocol_path)

        case IncuCmd():
            with runtime.timeit(entry):
                if metadata.sim_delay:
                    runtime.sleep(metadata.sim_delay or 0)
                incubator.execute(runtime, entry, cmd.action, cmd.incu_loc)

        case WaitForResource():
            raise ValueError('Cannot execute WaitForResource, run Command.make_resource_checkpoints first')

        case PFCmd():
            raise ValueError('TODO: execute PF')

        case SquidAcquire():
            for squid in runtime.time_resource_use(entry, runtime.squid):
                squid.load_config(cmd.config_path, cmd.project, cmd.plate)
                ok = squid.acquire()
                if not ok:
                    raise ValueError(f'Failed to start squid acquire, is squid busy?')

                # wait until it has started running:
                while squid.status().get('interactive'):
                    runtime.sleep(1.0)

                # wait until it has finished running:
                while not squid.status().get('interactive'):
                    runtime.sleep(1.0)

        case SquidStageCmd() as cmd:
            for squid in runtime.time_resource_use(entry, runtime.squid):
                match cmd.action:
                    case 'goto_loading':
                        squid.goto_loading()
                    case 'leave_loading':
                        squid.leave_loading()

        case FridgePutByBarcode():
            for fridge, barcode_reader in runtime.time_resource_use(entry, runtime.fridge_and_barcode_reader):
                barcode = barcode_reader.read_and_clear()
                if cmd.expected_barcode and cmd.expected_barcode != barcode:
                    raise ValueError(f'Plate has {barcode=!r} but expected {cmd.expected_barcode=!r}')
                loc = FridgeDB
                fridge.put(
                slot, *_ = FridgeSlots.where(FridgeSlot.occupant == None)
                next_cmd = FridgePut(loc=slot.loc, project=cmd.project, barcode=barcode)

        case FridgePut():
            [slot] = FridgeSlots.where(FridgeSlot.loc == cmd.loc)
            assert slot.occupant is None
            env.fridge.put(cmd.loc)
            occupant = FridgeOccupant(project=cmd.project, barcode=cmd.barcode)
            slot.replace(occupant=occupant).save(env.db)

        case FridgeGetByBarcode():
            occupant = FridgeOccupant(project=cmd.project, barcode=cmd.barcode)
            [slot] = FridgeSlots.where(FridgeSlot.occupant == occupant)
            return execute_one(FridgeGet(slot.loc, check_barcode=True), env)

        case FridgeGet():
            [slot] = FridgeSlots.where(FridgeSlot.loc == cmd.loc)
            assert slot.occupant is not None
            env.fridge.get(cmd.loc)
            if cmd.check_barcode and not env.is_sim:
                # check that the popped plate has the barcode we thought was in the fridge
                barcode = env.barcode_reader.read_and_clear()
                assert slot.occupant.barcode == barcode
            slot.replace(occupant=None).save(env.db)

        case FridgeCmd():
            env.fridge.action(cmd.action)

        case BarcodeClear():
            env.barcode_reader.clear()

        case _:
            raise ValueError(cmd)

    if effect := cmd.effect():
        runtime.apply_effect(effect, entry)

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, program: Program) -> Iterator[Runtime]:
    runtime = config.make_runtime()
    with runtime.excepthook():
        program.save(runtime.log_db)
        if program.world0:
            runtime.set_world(program.world0)
        yield runtime

def simulate_program(program: Program, sim_delays: dict[int, float] = {}, log_filename: str | None=None) -> DB:
    program, expected_ends = commandlib.prepare_program(program, sim_delays=sim_delays)

    with pbutils.timeit('quicksim'):
        quicksim_ends, _checkpoints = commandlib.quicksim(program.command, {}, cast(Any, estimate))

    commandlib.check_correspondence(program.command, optimizer_ends=expected_ends, quicksim_ends=quicksim_ends)

    cmd = program.command
    with pbutils.timeit('simulating'):
        config = simulate.replace(log_filename=log_filename)
        with make_runtime(config, program) as runtime_est:
            execute(cmd, runtime_est, Metadata())

    if not sim_delays:
        with pbutils.timeit('get simulation estimates'):
            states = runtime_est.log_db.get(CommandState).list()

        with pbutils.timeit('check schedule and simulation correspondence'):
            sim_ends={state.id: state.t for state in states}
            commandlib.check_correspondence(cmd, optimizer_ends=expected_ends, sim_ends=sim_ends)

    return runtime_est.log_db

def execute_simulated_program(config: RuntimeConfig, sim_db: DB, metadata: list[DBMixin]):
    programs = sim_db.get(Program).list()
    if len(programs) == 0:
        raise ValueError(f'No program stored in {sim_db.con.filename}')
    elif len(programs) > 1:
        raise ValueError(f'More than one program stored in {sim_db.con.filename}')
    else:
        [program] = programs
    cmd = program.command

    if program.metadata.protocol == 'cell-paint' and config.name == 'live':
        missing: list[BiotekCmd | BlueCmd] = []
        for k, _v in estimates.guesses.items():
            if isinstance(k, BiotekCmd) and k.protocol_path:
                missing += [k]
            if isinstance(k, BlueCmd) and k.protocol_path:
                missing += [k]
        if missing:
            from pprint import pformat
            raise ValueError('Missing timings for the following biotek commands:\n' + pformat(missing))

    with make_runtime(config, program) as runtime:
        if config.name == 'live':
            protocol_dirs = set[str]()
            for c in program.command.universe():
                if isinstance(c, BiotekCmd | BlueCmd) and c.protocol_path:
                    protocol_dir, _, _ = c.protocol_path.partition('/')
                    if protocol_dir:
                        protocol_dirs.add(protocol_dir)

            for protocol_dir in protocol_dirs:
                with pbutils.timeit(f'saving {protocol_dir} protocol files'):
                    protocol_paths.add_protocol_dir_as_sqlar(runtime.log_db, protocol_dir)

        states = sim_db.get(CommandState).list()
        with runtime.log_db.transaction:
            for state in states:
                if isinstance(state.cmd, WaitForCheckpoint | Checkpoint | Idle):
                    continue
                state.state = 'planned'
                state.save(runtime.log_db)

        runtime_metadata = RuntimeMetadata(
            start_time     = runtime.start_time,
            config_name    = config.name,
            log_filename   = config.log_filename or ':memory:',
        )
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        for data in metadata:
            data.save(runtime.log_db)

        cmd = program.command
        cmd = cmd.remove_scheduling_idles()
        with pbutils.timeit('execute'):
            execute(cmd, runtime, Metadata())

        runtime_metadata.completed = datetime.now()
        runtime_metadata = runtime_metadata.save(runtime.log_db)

        for line in runtime.get_log().group_durations_for_display():
            print(line)

def execute_program(config: RuntimeConfig, program: Program, metadata: list[DBMixin]=[], sim_delays: dict[int, float] = {}):
    db = simulate_program(program, sim_delays=sim_delays)
    execute_simulated_program(config, db, metadata)
