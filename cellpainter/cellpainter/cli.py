from __future__ import annotations
from typing import *

import argparse
import os
import sys
import json
import textwrap
import shlex
import re
from pathlib import Path

from dataclasses import *

from pbutils import show
import pbutils

from . import make_uml
from . import protocol
from . import estimates
from . import moves

from .commands import Program, ProgramMetadata
from . import execute
from .log import ExperimentMetadata, Log
from .moves import movelists
from .config import RuntimeConfig, configs
from .runtime import Runtime
from .small_protocols import small_protocols_dict, SmallProtocolArgs
from .protocol import CellPaintingArgs
from . import protocol_paths
from . import commandlib

from pbutils.mixins import DB
from pbutils.args import arg, option

@dataclass(frozen=True)
class Args(SmallProtocolArgs, CellPaintingArgs):
    config_name: str = arg(
        'simulate',
        enum=[option(c.name, c.name, help='Run with config ' + c.name) for c in configs]
    )

    protocol: str  = arg(
        enum=[
            option('cell-paint', 'cell-paint', help='Cell paint.'),
            *[
                option(name, name, help=p.doc)
                for name, p in small_protocols_dict().items()
            ]
        ]
    )
    log_filename:              str  = arg(help='Manually set the log filename instead of having a generated name based on date')
    protocol_dir:              str  = arg(default='automation_v5.0', help='Directory to read biotek .LHC files from on the windows server (relative to the protocol root).')
    force_update_protocol_paths: bool = arg(help='Update the protcol dir based on the windows server even if config is not --live.')

    timing_matrix:             bool = arg(help='Print a timing matrix.')

    run_program_in_log_filename: str  = arg(help='Run the program stored in a log file. Used to run simulated programs from the gui.')

    start_from_stage:          str  = arg(help="Start from this stage (example: 'Mito, plate 2')")
    list_stages:               bool = arg(help="List the stages and then exit")

    visualize:                 bool = arg(help='Run detailed protocol visualizer')
    init_cmd_for_visualize:    str  = arg(help='Starting cmdline for visualizer')
    log_file_for_visualize:    str  = arg(help='Display a log file in visualizer')
    sim_delays:                str  = arg(help='Add simulated delays, example: 8:300 for a slowdown to 300s on command with id 8. Separate multiple values with comma.')

    list_imports:              bool = arg(help='Print the imported python modules for type checking.')

    add_estimates_from:        str  = arg(help='Add timing estimates from a log file')
    add_estimates_dest:        str  = arg(default='estimates.jsonl', help='Add timing estimates to this file (default: estimates.jsonl)')

    list_robotarm_programs:    bool = arg(help='List the robot arm programs')
    inspect_robotarm_programs: bool = arg(help='Inspect steps of robotarm programs')
    robotarm_send:             str  = arg(help='Send a raw program to the robot arm')
    ur_speed:                  int  = arg(default=100, help='Robot arm speed [1-100]')
    pf_speed:                  int  = arg(default=50, help='Robot arm speed [1-100]')
    json_arg:                  str  = arg(help='Give arguments as json on the command line')
    yes:                       bool = arg(help='Assume yes in confirmation questions')
    make_uml:                  str  = arg(help='Write uml in dot format to the given path and exit')

    desc: str = arg(help='Experiment description metadata, example: "specs935-v1"')
    operators:  str = arg(help='Experiment metadata, example: "Amelie and Christa"')

def args_to_str(args: Args):
    parts: list[str] = []
    for f in fields(args):
        k = f.name
        d = f.default_factory() if callable(f.default_factory) else f.default
        v = getattr(args, k)
        if k == 'initial_fridge_contents':
            continue
        k = k.replace('_', '-')
        if v != d:
            if k == 'params' and isinstance(v, list):
                parts += [*v]
            elif isinstance(v, list):
                parts += [f'--{k}', *v]
            elif isinstance(v, bool):
                if v:
                    parts += [f'--{k}']
            else:
                parts += [f'--{k}', str(v)]
    return shlex.join(parts)

def main():
    args, parser = arg.parse_args(Args, description='Make the lab robots do things.')
    if args.json_arg:
        args = Args(**json.loads(args.json_arg))
    return main_with_args(args, parser)

def cmdline_to_log(cmdline: str):
    cmdname = 'cellpainter'
    print(cmdline, shlex.split(cmdline))
    args, _ = arg.parse_args(Args, args=[cmdname, *shlex.split(cmdline)], exit_on_error=False)
    pbutils.pr(args)
    if args.log_file_for_visualize:
        return Log.connect(args.log_file_for_visualize)
    else:
        p = args_to_program(args)
        assert p, 'no program from these arguments!'
        return Log(execute.simulate_program(p, sim_delays=parse_sim_delays(args)))

def main_with_args(args: Args, parser: argparse.ArgumentParser | None=None):

    if args.make_uml:
        make_uml.visualize_modules(args.make_uml)
        sys.exit(0)

    if args.list_imports:
        my_dir = os.path.dirname(__file__)
        for m in sys.modules.values():
            path = getattr(m, '__file__', None)
            if path and path.startswith(my_dir):
                print(path)
        sys.exit(0)

    if args.add_estimates_from:
        estimates.add_estimates_from(args.add_estimates_from, path=args.add_estimates_dest)
        sys.exit(0)

    config: RuntimeConfig = RuntimeConfig.lookup(args.config_name)

    arms = Runtime.init(config.replace(log_filename=None).only_arm())
    arms.ur and arms.ur.set_speed(args.ur_speed)
    arms.pf and arms.pf.set_speed(args.pf_speed)

    config = config.replace(
        log_filename=args.log_filename,
    )

    # print('config =', show(config))
    # print('args =', show(args))

    em = ExperimentMetadata(desc=args.desc, operators=args.operators)

    if args.timing_matrix:
        out: list[list[Any]] = []
        # for incu in ['1200', 'X']:
        for incu in ['X']:
            for N in [x + 1 for x in range(18)]:
                for two_final_washes in [True]:
                    for interleave in [True]:
                        args2 = replace(args,
                            protocol='cell-paint',
                            interleave=interleave,
                            two_final_washes=two_final_washes,
                            incu=incu,
                            batch_sizes=str(N)
                        )
                        p = args_to_program(args2)
                        if p:
                            try:
                                sim_db = execute.simulate_program(p)
                                G = Log(sim_db).group_durations()
                                incubations = [times for event_name, times in G.items() if 'incubation' in event_name]
                                if incubations:
                                    X = incubations[0][0]
                                else:
                                    X = float('NaN')
                                T = pbutils.pp_secs(Log(sim_db).time_end())
                            except:
                                T = float('NaN')
                                X = float('NaN')
                            print(f'{N=}, {X=}, {T=}')
                            out += [[N, X, T]]
        print()
        print(*'N incu T'.split(), sep='\t')
        for line in out:
            print(*line, sep='\t')
        quit()

    if args.force_update_protocol_paths or config.name == 'live':
        protocol_paths.update_protocol_paths()

    if args.visualize:
        from . import protocol_vis as pv

        _cmdname, *argv = [arg for arg in sys.argv if not arg.startswith('--vi')]
        if args.init_cmd_for_visualize:
            cmdline0 = args.init_cmd_for_visualize
        else:
            cmdline0 = shlex.join(argv)

        pv.start(cmdline0, cmdline_to_log)

    elif args.list_stages:
        pbutils.pr(args_to_stages(args))

    elif args.run_program_in_log_filename:
        with DB.open(args.run_program_in_log_filename) as db:
            execute.execute_simulated_program(config, db, [
                db.get(ExperimentMetadata).one_or(em),
                db.get(ProgramMetadata).one_or(
                    ProgramMetadata(protocol=f'{args.run_program_in_log_filename=}')
                ),
            ])

    elif p := args_to_program(args):
        if config.name != 'simulate' and p.doc and not args.yes:
            confirm(p.doc)

        if not args.log_filename:
            filename_parts = [
                pbutils.now_str_for_filename(),
                p.metadata.protocol,
                config.name,
            ]
            log_filename = ' '.join(filename_parts)
            log_filename = 'logs/' + log_filename.replace(' ', '_') + '.db'
            config = config.replace(log_filename=log_filename)

        if log_filename := config.log_filename:
            log_path = Path(log_filename)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.unlink(missing_ok=True)

        try:
            execute.execute_program(config, p, [em, p.metadata], sim_delays=parse_sim_delays(args))
        except ValueError as e:
            print(e, file=sys.stderr,)
        except:
            raise

    elif args.robotarm_send:
        runtime = Runtime.init(config)
        assert runtime.ur
        runtime.ur.execute_moves([moves.RawCode(args.robotarm_send)], name='raw')

    elif args.list_robotarm_programs:
        for name in movelists.keys():
            print(name)

    elif args.inspect_robotarm_programs:
        for k, v in movelists.items():
            m = re.search(r'\d+', k)
            if not m or m.group(0) in {"19", "21"}:
                print()
                print(k + ':\n' + textwrap.indent(v.describe(), '  '))

    else:
        assert parser
        parser.print_help()

    if estimates.guesses:
        print('Guessed these times:')
        pbutils.pr(estimates.guesses)

def args_to_filename(args: Args) -> str:
    pm: ProgramMetadata
    if args.run_program_in_log_filename:
        with Log.open(args.run_program_in_log_filename) as g:
            if (p := g.program()):
                pm = p.metadata
            else:
                pm = g.program_metadata() or ProgramMetadata()
            if (em := g.experiment_metadata()):
                desc = em.desc
            else:
                desc = args.desc
    elif (p := args_to_program(args)):
        pm = p.metadata
        desc = args.desc
    else:
        pm = ProgramMetadata()
        desc = args.desc
    now_str = pbutils.now_str_for_filename()
    program_name = pm.protocol
    desc = re.sub(r'[^\w\d\-]', '_', desc)
    config_name = args.config_name
    log_filename = f'logs/{now_str}-{program_name}-{desc}-{config_name}.db'
    log_filename = re.sub(r'_{2,}', '_', log_filename)
    log_filename = re.sub(r'-{2,}', '-', log_filename)
    return log_filename

def normalize_args(args: Args) -> str:
    return str(replace(args, desc='', operators=''))

@pbutils.cache_by(normalize_args)
def args_to_stages(args: Args) -> list[str] | None:
    p = args_to_program(args)
    if p:
        return p.command.stages()
    else:
        return None

@pbutils.cache_by(normalize_args)
def args_to_program(args: Args) -> Program | None:
    paths = protocol_paths.get_protocol_paths()[args.protocol_dir]

    program: Program | None = None
    if args.protocol == 'cell-paint':
        with pbutils.timeit('generating program'):
            protocol_config = protocol.make_protocol_config(paths, args)
            batch_sizes = pbutils.read_commasep(args.batch_sizes, int)
            program = protocol.cell_paint_program(
                batch_sizes=batch_sizes,
                protocol_config=protocol_config,
            )

    elif args.protocol:
        name = args.protocol.replace('-', '_')
        p = small_protocols_dict().get(name)
        if p:
            program = p.make(args)
            program = program.replace(
                metadata=ProgramMetadata(
                    protocol=args.protocol,
                    num_plates=args.num_plates,
                ),
                doc=p.doc
            )
        else:
            raise ValueError(f'Unknown protocol: {name} (available: {", ".join(small_protocols_dict().keys())})')

    if program:
        if args.start_from_stage:
            if args.start_from_stage != program.command.stages()[0]:
                program = commandlib.remove_stages(program, args.start_from_stage)
        return program
    else:
        return None

def parse_sim_delays(args: Args):
    sim_delays: dict[int, float] = {}
    for kv in args.sim_delays.split(','):
        if kv:
            id, delay = kv.split(':')
            if id.isnumeric():
                sim_delays[int(id)] = float(delay)

    if sim_delays:
        print('sim_delays =', show(sim_delays))
    return sim_delays

def confirm(s: str):
    color = pbutils.Color()
    print(color.red('*' * 80))
    print()
    print(textwrap.indent(textwrap.dedent(s.strip('\n')), '    ').rstrip('\n'))
    print()
    print(color.red('*' * 80))
    v = input('Continue? [y/n] ')
    if v.strip() != 'y':
        raise ValueError('Program aborted by user')
    else:
        print('continuing...')

if __name__ == '__main__':
    main()
