from __future__ import annotations
from typing import *
from dataclasses import *

import contextlib

from .commands import *

from .log import (
    CommandState,
    RuntimeMetadata,
    CommandWithMetadata,
)

from .runtime import RuntimeConfig, Runtime
from . import commandlib
import pbutils
from .moves import movelists
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
            secs = Symbolic.wrap(cmd.secs).unwrap()
            entry = entry.merge(Metadata(est=round(secs, 3)))
            with runtime.timeit(entry):
                runtime.sleep(secs)

        case Checkpoint():
            with runtime.timeit(entry):
                runtime.checkpoint(cmd.name, entry)

        case WaitForCheckpoint():
            plus_secs = Symbolic.wrap(cmd.plus_secs).unwrap()
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
            movelist = movelists.get(cmd.program_name)
            if movelist is None:
                raise ValueError(f'Missing robotarm move {cmd.program_name}')
            with_gripper = runtime.config.ur_env.mode != 'execute no gripper'
            script = movelist.make_ur_script(with_gripper=with_gripper, name=cmd.program_name)
            for ur in runtime.time_resource_use(entry, runtime.ur):
                ur.execute_script(script)

        case PFCmd():
            movelist = movelists.get(cmd.program_name)

            if movelist is None:
                raise ValueError(f'Missing robotarm move {cmd.program_name}')

            do_move = True

            if cmd.only_if_no_barcode:
                reader = runtime.barcode_reader
                do_move = reader and reader.read() == ''

            if do_move:
                for pf in runtime.time_resource_use(entry, runtime.pf):
                    pf.execute_moves(movelist)

        case BiotekCmd():
            bioteks.execute(runtime, entry, cmd.machine, cmd.protocol_path, cmd.action)

        case BlueCmd():
            bluewash.execute(runtime, entry, action=cmd.action, protocol_path=cmd.protocol_path)

        case IncuCmd(action=action):
            incubator.execute(runtime, entry, action, cmd.incu_loc)

        case DLidCheckStatusCmd():
            for dlid in runtime.time_resource_use(entry, runtime.dlid):
                dlid_ids = {
                    'B12': '1',
                    'B14': '2',
                }
                dlid_id = dlid_ids[cmd.dlid_loc]
                actual_status = dlid.get_status(dlid_id)
                if actual_status != cmd.status:
                    if actual_status == 'free':
                        raise ValueError(f'Vacuum delidding machine error: DLid D{dlid_id} on {cmd.dlid_loc} should be holding a lid but is not.')
                    else:
                        raise ValueError(f'Vacuum delidding machine error: DLid D{dlid_id} on {cmd.dlid_loc} should not be holding a lid but is not.')

        case SquidAcquire():
            for squid in runtime.time_resource_use(entry, runtime.squid):
              if cmd.config_path != 'noop':
                squid.load_config(
                    file_path=cmd.config_path,
                    project_override=cmd.project,
                    plate_override=cmd.plate
                )
                ok = squid.acquire()
                if not ok:
                    raise ValueError(f'Failed to start squid acquire. Is squid busy?')

                # wait until it has started running:
                while squid.status().get('interactive'):
                    runtime.sleep(1.0)

                # wait until it has finished running:
                while not squid.status().get('interactive'):
                    if (progress_bar_text := squid.status().get('progress_bar_text')):
                        runtime.set_progress_text(entry, text=progress_bar_text)

                    runtime.sleep(1.0)

        case NikonAcquire():
            for nikon in runtime.time_resource_use(entry, runtime.nikon):
                if cmd.job_project == 'noop':
                    break
                nikon.RunJob(
                    job_project=cmd.job_project,
                    job_name=cmd.job_name,
                    project=cmd.project,
                    plate=cmd.plate,
                )
                while nikon.is_running():
                    status = nikon.screen_scraper_status()
                    well, countdown = status.get('well'), status.get('countdown')
                    if countdown:
                        text = f'{well}, time remaining: {countdown}'
                        if well:
                             text = f'{well}, {text}'
                        runtime.set_progress_text(entry, text=text)
                    runtime.sleep(1.0)

        case NikonStageCmd() as cmd:
            for nikon, nikon_stage in runtime.time_resource_use(entry, runtime.nikon_and_stage):
                match cmd.action:
                    case 'goto_loading':
                        nikon.StgMoveZ(0)
                        runtime.wait_while(nikon.is_running)
                        nikon.StgMoveToA01()
                        runtime.wait_while(nikon.is_running)

                        nikon_stage.open()
                        runtime.sleep(1.0)
                        runtime.wait_while(nikon_stage.is_busy)

                    case 'leave_loading':
                        nikon_stage.close()
                        runtime.sleep(1.0)
                        runtime.wait_while(nikon_stage.is_busy)

                    case 'init_laser':
                        nikon.InitLaser()
                        runtime.wait_while(nikon.is_running)
                        nikon.CloseAllDocuments()
                        runtime.wait_while(nikon.is_running)

                    case 'get_status':
                        nikon.status()

                    case 'check_protocol_exists':
                        if cmd.job_project == 'noop':
                            break
                        protocols = nikon.list_protocols()
                        if cmd.job_name_dict() not in protocols:
                            raise ValueError(f'Nikon cannot find {cmd.job_name_dict()!r}')

        case SquidStageCmd() as cmd:
            for squid in runtime.time_resource_use(entry, runtime.squid):
                match cmd.action:
                    case 'goto_loading':
                        squid.goto_loading()
                    case 'leave_loading':
                        squid.leave_loading()
                    case 'get_status':
                        squid.status()
                    case 'check_protocol_exists':
                        protocols = ['noop', *squid.list_protocols()]
                        if cmd.protocol not in protocols:
                            raise ValueError(f'Squid cannot find {cmd.protocol!r}')

        case FridgeInsert():
            for fridge, barcode_reader in runtime.time_resource_use(entry, runtime.fridge_and_barcode_reader):
                if cmd.assume_barcode:
                    barcode = cmd.assume_barcode
                else:
                    barcode = barcode_reader.read_and_clear()
                if not barcode:
                    raise ValueError(f'No barcode registered')
                if cmd.expected_barcode and cmd.expected_barcode != barcode:
                    raise ValueError(f'Plate has {barcode=!r} but expected {cmd.expected_barcode=!r}')
                fridge.insert(barcode, cmd.project)

        case FridgeEject():
            for fridge, barcode_reader in runtime.time_resource_use(entry, runtime.fridge_and_barcode_reader):
                barcode_reader.clear()
                fridge.eject(plate=cmd.plate, project=cmd.project)
                runtime.sleep(1.0)
                barcode = barcode_reader.read_and_clear()
                if not cmd.check_barcode:
                    if barcode != cmd.plate:
                        import sys
                        print(f'Plate has {barcode=!r} but expected {cmd.plate=!r}. Ignoring because {cmd=}.', file=sys.stderr)
                elif barcode != cmd.plate:
                    raise ValueError(f'Plate has {barcode=!r} but expected {cmd.plate=!r}')

        case FridgeCmd(action=action):
            for fridge in runtime.time_resource_use(entry, runtime.fridge):
                match action:
                    case 'get_status':
                        fridge.get_status()
                    case 'reset_and_activate':
                        fridge.reset_and_activate()

        case BarcodeClear():
            for barcode_reader in runtime.time_resource_use(entry, runtime.barcode_reader):
                barcode_reader.clear()

        case WaitForResource():
            raise ValueError('Cannot execute WaitForResource, run Command.make_resource_checkpoints first')

        case _:
            raise ValueError(f'Unknown command {cmd}')

    if effect := cmd.effect():
        runtime.apply_effect(effect, entry, fatal_errors=runtime.config.name == 'simulate')

@contextlib.contextmanager
def make_runtime(config: RuntimeConfig, program: Program) -> Iterator[Runtime]:
    runtime = Runtime.init(config)
    with runtime.excepthook():
        program.save(runtime.log_db)
        if program.world0:
            runtime.set_world(program.world0)
        yield runtime

def simulate_program(program: Program, sim_delays: dict[int, float] = {}, log_filename: str | None=None) -> DB:
    program, expected_ends = commandlib.prepare_program(program, sim_delays=sim_delays)

    with pbutils.timeit('check quick simulation'):
        quicksim_ends, _checkpoints = commandlib.quicksim(program.command, {}, cast(Any, estimate))
        commandlib.check_correspondence(program.command, optimizer_ends=expected_ends, quicksim_ends=quicksim_ends)

    cmd = program.command

    with pbutils.timeit('check deep simulation'):
        config = RuntimeConfig.simulate().replace(log_filename=log_filename)
        with make_runtime(config, program) as runtime_est:
            execute(cmd, runtime_est, Metadata())

        if not sim_delays:
            states = runtime_est.log_db.get(CommandState).list() # get simulation estimates
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
