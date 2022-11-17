from __future__ import annotations
from typing import *

import argparse
import os
import sys
import json
import textwrap
import shlex
import re
import pickle

from dataclasses import *

from pbutils import show
import pbutils

from . import make_uml
from . import protocol
from . import estimates
from . import moves

from .commands import Program
from . import execute
from .log import Log
from .moves import movelists
from .runtime import RuntimeConfig, configs, config_lookup
from .small_protocols import small_protocols_dict, SmallProtocolArgs
from . import protocol_paths

from pbutils.mixins import DB
from pbutils.args import arg, option

@dataclass(frozen=True)
class Args:
    config_name: str = arg(
        'dry-run',
        enum=[option(c.name, c.name, help='Run with config ' + c.name) for c in configs]
    )
    cell_paint:                str  = arg(help='Cell paint with batch sizes separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    incu:                      str  = arg(default='1200,1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    interleave:                bool = arg(help='Interleave plates, required for 7 plate batches')
    two_final_washes:          bool = arg(help='Use two shorter final washes in the end, required for big batch sizes, required for 8 plate batches')
    lockstep:                  bool = arg(help='Allow steps to overlap: first plate PFA starts before last plate Mito finished and so on, required for 10 plate batches')
    log_filename:              str  = arg(help='Manually set the log filename instead of having a generated name based on date')
    protocol_dir:              str  = arg(default='automation_v5.0', help='Directory to read biotek .LHC files from on the windows server (relative to the protocol root).')
    force_update_protocol_dir: bool = arg(help='Update the protcol dir based on the windows server even if config is not --live.')

    timing_matrix:             bool = arg(help='Print a timing matrix.')

    run_program_in_log_filename: str  = arg(help='Run the program stored in a log file. Used to run simulated programs from the gui.')

    small_protocol:            str  = arg(
        enum=[
            option(name, name, help=p.doc)
            for name, p in small_protocols_dict.items()
        ]
    )
    num_plates:                int  = arg(help='For some protocols only: number of plates')
    params:                    list[str] = arg(help='For some protocols only: more parameters')

    start_from_stage:          str  = arg(help="Start from this stage (example: 'Mito, plate 2')")
    list_stages:               bool = arg(help="List the stages and then exit")

    visualize:                 bool = arg(help='Run detailed protocol visualizer')
    init_cmd_for_visualize:    str  = arg(help='Starting cmdline for visualizer')
    log_file_for_visualize:    str  = arg(help='Display a log file in visualizer')
    sim_delays:                str  = arg(help='Add simulated delays, example: 8:300 for a slowdown to 300s on command with id 8. Separate multiple values with comma.')

    list_imports:              bool = arg(help='Print the imported python modules for type checking.')

    add_estimates_from:        str  = arg(help='Add timing estimates from a log file')

    list_robotarm_programs:    bool = arg(help='List the robot arm programs')
    inspect_robotarm_programs: bool = arg(help='Inspect steps of robotarm programs')
    robotarm_send:             str  = arg(help='Send a raw program to the robot arm')
    robotarm_speed:            int  = arg(default=100, help='Robot arm speed [1-100]')
    json_arg:                  str  = arg(help='Give arguments as json on the command line')
    yes:                       bool = arg(help='Assume yes in confirmation questions')
    make_uml:                  str  = arg(help='Write uml in dot format to the given path and exit')

def main():
    args, parser = arg.parse_args(Args, description='Make the lab robots do things.')
    if args.json_arg:
        args = Args(**json.loads(args.json_arg))
    return main_with_args(args, parser)

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

    config: RuntimeConfig = config_lookup(args.config_name)
    config = config.replace(
        robotarm_speed=args.robotarm_speed,
        log_filename=args.log_filename,
    )

    print('config =', show(config))
    print('args =', show(args))

    if args.timing_matrix:
        out: list[list[Any]] = []
        for incu in ['1200', 'X']:
            for N in [x + 1 for x in range(10)]:
                for two_final_washes in [False, True]:
                    for interleave in [False, True]:
                        args2 = replace(args, interleave=interleave, two_final_washes=two_final_washes, incu=incu, cell_paint=str(N))
                        p = args_to_program(args2)
                        if p:
                            try:
                                sim_db = execute.simulate_program(p)
                                T = pbutils.pp_secs(Log(sim_db).time_end())
                            except:
                                T = float('NaN')
                            print(f'{N=}, {interleave=}, {two_final_washes=}, {incu=}, {T=}')
                            out += [[
                                N,
                                'interleave' if interleave else 'linear',
                                '2*3X' if two_final_washes else '5X',
                                incu,
                                T
                            ]]
        print()
        print(*'N interleave final incu T'.split(), sep='\t')
        for line in out:
            print(*line, sep='\t')
        quit()

    if args.force_update_protocol_dir or config.name == 'live':
        protocol_paths.update_protocol_dir(args.protocol_dir)

    if args.visualize:
        from . import protocol_vis as pv
        cmdname, *argv = [arg for arg in sys.argv if not arg.startswith('--vi')]
        if args.init_cmd_for_visualize:
            cmdline0 = args.init_cmd_for_visualize
        else:
            cmdline0 = shlex.join(argv)
        def cmdline_to_log(cmdline: str):
            args, _ = arg.parse_args(Args, args=[cmdname, *shlex.split(cmdline)], exit_on_error=False)
            pbutils.pr(args)
            if args.log_file_for_visualize:
                return Log.open(args.log_file_for_visualize)
            else:
                p = args_to_program(args)
                assert p, 'no program from these arguments!'
                return Log(execute.simulate_program(p, sim_delays=parse_sim_delays(args)))
        pv.start(cmdline0, cmdline_to_log)

    elif args.list_stages:
        pbutils.pr(args_to_stages(args))

    elif args.run_program_in_log_filename:
        with DB.open(args.run_program_in_log_filename) as db:
            execute.execute_simulated_program(config, db)

    elif p := args_to_program(args):
        if config.name != 'dry-run' and p.doc and not args.yes:
            confirm(p.doc)

        if not args.log_filename:
            metadata = {
                'start_time': pbutils.now_str_for_filename(),
                **p.metadata,
                'config_name': config.name,
            }
            log_filename = ' '.join(['event log', *metadata.values()])
            log_filename = 'logs/' + log_filename.replace(' ', '_') + '.db'
            config = config.replace(log_filename=log_filename)

        log = execute.execute_program(config, p, sim_delays=parse_sim_delays(args))
        if re.match('time.bioteks', p.metadata.get('program', '')) and config.name == 'live':
            estimates.add_estimates_from('estimates.json', log)

    elif args.robotarm_send:
        runtime = config.make_runtime()
        arm = runtime.get_robotarm()
        arm.execute_moves([moves.RawCode(args.robotarm_send)], name='raw')
        arm.close()

    elif args.list_robotarm_programs:
        for name in movelists.keys():
            print(name)

    elif args.inspect_robotarm_programs:
        for k, v in movelists.items():
            m = re.search(r'\d+', k)
            if not m or m.group(0) in {"19", "21"}:
                print()
                print(k + ':\n' + textwrap.indent(v.describe(), '  '))

    elif args.add_estimates_from:
        estimates.add_estimates_from('estimates.json', args.add_estimates_from)

    else:
        assert parser
        parser.print_help()

    if estimates.guesses:
        print('Guessed these times:')
        pbutils.pr(estimates.guesses)

@pbutils.cache_by(lambda args: str(args))
def args_to_stages(args: Args) -> list[str] | None:
    p = args_to_program(args)
    if p:
        return p.command.stages()
    else:
        return None

def args_to_program(args: Args) -> Program | None:
    paths =  protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = protocol.make_protocol_config(paths, args)

    program: Program | None = None
    if args.cell_paint:
        with pbutils.timeit('generating program'):
            batch_sizes = pbutils.read_commasep(args.cell_paint, int)
            program = protocol.cell_paint_program(
                batch_sizes=batch_sizes,
                protocol_config=protocol_config,
            )
            program = program.replace(metadata=program.metadata | {
                'program': 'cell_paint',
                'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
            })

    elif args.small_protocol:
        name = args.small_protocol.replace('-', '_')
        p = small_protocols_dict.get(name)
        if p:
            small_args = SmallProtocolArgs(
                num_plates = args.num_plates,
                params = args.params,
                protocol_dir = args.protocol_dir,
            )
            program = p.make(small_args)
            program = program.replace(metadata={'program': p.name}, doc=p.doc)
        else:
            raise ValueError(f'Unknown protocol: {name} (available: {", ".join(small_protocols_dict.keys())})')

    if program:
        if args.start_from_stage:
            if args.start_from_stage != program.command.stages()[0]:
                program = execute.remove_stages(program, args.start_from_stage)
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
