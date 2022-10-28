from __future__ import annotations
from typing import *

import argparse
import os
import sys
import json
import textwrap
import shlex
import re

from datetime import timedelta
from dataclasses import *

from pbutils import show
import pbutils

from . import commands
from . import make_uml
from . import protocol
from . import resume
from . import estimates
from . import moves

from .execute import execute_program
from .log import Log
from .moves import movelists
from .runtime import RuntimeConfig, configs, config_lookup
from .small_protocols import small_protocols_dict, SmallProtocolArgs
from . import protocol_paths

from pbutils.args import arg, option

def ATTENTION(s: str):
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

@dataclass(frozen=True)
class Args:
    config_name: str = arg(
        'dry-run',
        enum=[option(c.name, c.name, help='Run with config ' + c.name) for c in configs]
    )
    cell_paint:                str  = arg(help='Cell paint with batch sizes of BS, separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    incu:                      str  = arg(default='1200,1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    interleave:                bool = arg(help='Interleave plates, required for 7 plate batches')
    two_final_washes:          bool = arg(help='Use two shorter final washes in the end, required for big batch sizes, required for 8 plate batches')
    lockstep:                  bool = arg(help='Allow steps to overlap: first plate PFA starts before last plate Mito finished and so on, required for 10 plate batches')
    start_from_pfa:            bool = arg(help='Start from PFA (in room temperature). Use this if you have done Mito manually beforehand')
    log_filename:              str  = arg(help='Manually set the log filename instead of having a generated name based on date')
    protocol_dir:              str  = arg(default='automation_v5.0', help='Directory to read biotek .LHC files from on the windows server (relative to the protocol root).')
    force_update_protocol_dir: bool = arg(help='Update the protcol dir based on the windows server even if config is not --live.')

    timing_matrix:             bool = arg(help='Print a timing matrix.')

    small_protocol:            str  = arg(
        enum=[
            option(name, name, help=p.doc)
            for name, p in small_protocols_dict.items()
        ]
    )
    num_plates:                int  = arg(help='For some protocols only: number of plates')
    params:                    list[str] = arg(help='For some protocols only: more parameters')

    remove_until_stage:        str  = arg(help='Remove commands before this stage')

    resume:                    str  = arg(help='Resume program given a log file')
    resume_skip:               str  = arg(help='Comma-separated list of simple_id:s to skip (washes and dispenses)')
    resume_drop:               str  = arg(help='Comma-separated list of plate_id:s to drop')
    resume_time_now:           str  = arg(help='Use this time as current time instead of datetime.now()')

    test_resume:               str  = arg(help='Test resume by running twice, second time by resuming from just before the argument id')
    test_resume_delay:         int  = arg(help='Test resume simulated delay')

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
                                res = execute_program(
                                    config_lookup('dry-run').replace(log_to_file=False),
                                    p.program, {}, for_visualizer=True
                                )
                                T = pbutils.pp_secs(res.max_t())
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
                return Log.read_jsonl(args.log_file_for_visualize)
            else:
                p = args_to_program(args)
                assert p, 'no program from these arguments!'
                return execute_program(config, p.program, {}, for_visualizer=True, sim_delays=p.sim_delays)
        pv.start(cmdline0, cmdline_to_log)

    elif args.test_resume:
        log_file1 = 'logs/test_resume.jsonl'
        log_file2 = 'logs/test_resume_partial.jsonl'
        args1 = replace(args, test_resume='', log_filename=log_file1)
        main_with_args(args1, parser)
        log = Log.read_jsonl(log_file1)
        runtime_metadata = log.runtime_metadata()
        assert runtime_metadata
        run_file = runtime_metadata.running_log_filename
        run = Log.read_jsonl(run_file)
        log = log.drop_after(float(args.test_resume))
        run = run.drop_after(float(args.test_resume))
        log.write_jsonl(log_file2)
        run.write_jsonl(run_file)
        resume_time_now = log.zero_time() + timedelta(seconds=log[-1].t) + timedelta(seconds=args.test_resume_delay)
        args2 = replace(args, test_resume='', resume=log_file2, resume_time_now=str(resume_time_now))
        main_with_args(args2, parser)

    elif args.resume:
        resume.execute_resume(
            config,
            args.resume,
            resume_time_now=args.resume_time_now or None,
            skip=pbutils.read_commasep(args.resume_skip),
            drop=pbutils.read_commasep(args.resume_drop),
        )

    elif p := args_to_program(args):
        if config.name != 'dry-run' and p.doc and not args.yes:
            ATTENTION(p.doc)
        log = execute_program(config, p.program, p.metadata, sim_delays=p.sim_delays)
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

@dataclass(frozen=True)
class Program:
    program: commands.Command
    metadata: dict[str, Any]
    doc: str = ''
    sim_delays: dict[str, float] = field(default_factory=dict)

def args_to_program(args: Args) -> Program | None:

    sim_delays: dict[str, float] = {}
    for kv in args.sim_delays.split(','):
        if kv:
            id, delay = kv.split(':')
            sim_delays[id] = float(delay)

    if sim_delays:
        print('delays =', show(sim_delays))

    paths =  protocol_paths.get_protocol_paths()[args.protocol_dir]
    protocol_config = protocol.make_protocol_config(paths, args)

    if args.cell_paint:
        batch_sizes = pbutils.read_commasep(args.cell_paint, int)
        program = protocol.cell_paint_program(
            batch_sizes=batch_sizes,
            protocol_config=protocol_config,
            remove_until_stage=args.remove_until_stage or None,
        )
        return Program(program, {
            'program': 'cell_paint',
            'batch_sizes': ','.join(str(bs) for bs in batch_sizes),
        }, sim_delays=sim_delays)

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
            return Program(program, {'program': p.name}, doc=p.doc, sim_delays=sim_delays)
        else:
            raise ValueError(f'Unknown protocol: {name} (available: {", ".join(small_protocols_dict.keys())})')

    else:
        return None

if __name__ == '__main__':
    main()
