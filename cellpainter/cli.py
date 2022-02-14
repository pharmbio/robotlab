from __future__ import annotations
from typing import *
import typing

import argparse
import os
import sys
import json
import textwrap
import shlex
import re

from datetime import timedelta
from dataclasses import dataclass, field, fields, Field, replace

from . import commands
from . import make_uml
from . import protocol
from . import resume
from . import utils
from . import estimates
from . import moves

from .execute import execute_program
from .log import Log
from .moves import movelists
from .runtime import RuntimeConfig, configs, config_lookup
from .small_protocols import small_protocols_dict, SmallProtocolArgs
from .utils import show

A = TypeVar('A')

@dataclass(frozen=True)
class option:
    name: str
    value: Any
    help: str = ''

@dataclass(frozen=True)
class Nothing:
    pass

nothing = Nothing()

@dataclass(frozen=True)
class Arg:
    helps: dict[Any, str] = field(default_factory=dict)
    enums: dict[Any, list[option]] = field(default_factory=dict)
    def __call__(self, default: A | Nothing = nothing, help: str | Callable[..., Any] | None = None, enum: list[option] | None = None) -> A:
        f: Field[A]
        def default_factory():
            # at this point we know f.type
            if default == nothing:
                f_type: str = f.type # type: ignore
                return eval(f_type)()
            else:
                return default
        f = field(default_factory=default_factory) # type: ignore
        if callable(help):
            help = help.__doc__
        if help:
            self.helps[f] = utils.doc_header(help)
        if enum:
            self.enums[f] = enum
        return f # type: ignore

    def parse_args(self, as_type: Type[A], args: None | list[str] = None, **kws: Any) -> tuple[A, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser(**kws)
        for f in fields(as_type):
            enum = self.enums.get(f)
            name = '--' + f.name.replace('_', '-')
            assert callable(f.default_factory)
            default = f.default_factory()
            if enum:
                parser.add_argument(name, default=default, help=argparse.SUPPRESS)
                for opt in enum:
                    opt_name = '--' + opt.name.replace('_', '-')
                    parser.add_argument(opt_name, dest=f.name, action="store_const", const=opt.value, help=opt.help)
            else:
                f_type = eval(f.type)
                if f_type == list or typing.get_origin(f_type) == list:
                    parser.add_argument(dest=f.name, default=default, nargs="*", help=self.helps.get(f))
                elif f_type == bool:
                    action = 'store_false' if default else 'store_true'
                    parser.add_argument(name, default=bool(default), action=action, help=self.helps.get(f))
                else:
                    parser.add_argument(name, default=default, metavar='X', type=f_type, help=self.helps.get(f))
        v, unknown = parser.parse_known_args(args)
        if unknown:
            raise ValueError('Unknown args: ' + '\n'.join(unknown))
        return as_type(**v.__dict__), parser

arg = Arg()

def ATTENTION(s: str):
    color = utils.Color()
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

    small_protocol:            str  = arg(
        enum=[
            option(name, name, help=p.doc)
            for name, p in small_protocols_dict.items()
        ]
    )
    num_plates:                int  = arg(help='For some protocols only: number of plates')
    params:                    list[str] = arg(help='For some protocols only: more parameters')

    resume:                    str  = arg(help='Resume program given a log file')
    resume_skip:               str  = arg(help='Comma-separated list of simple_id:s to skip (washes and dispenses)')
    resume_drop:               str  = arg(help='Comma-separated list of plate_id:s to drop')
    resume_time_now:           str  = arg(help='Use this time as current time instead of datetime.now()')

    test_resume:               str  = arg(help='Test resume by running twice, second time by resuming from just before the argument id')
    test_resume_delay:         int  = arg(help='Test resume simulated delay')

    visualize:                 bool = arg(help='Run visualizer')
    visualize_init_cmd:        str  = arg(help='Starting cmdline for visualizer')

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

    if args.visualize:
        from . import protocol_vis as pv
        cmdname, *argv = [arg for arg in sys.argv if not arg.startswith('--vi')]
        if args.visualize_init_cmd:
            cmdline0 = args.visualize_init_cmd
        else:
            cmdline0 = shlex.join(argv)
        def cmdline_to_log(cmdline: str):
            args, _ = arg.parse_args(Args, args=[cmdname, *shlex.split(cmdline)], exit_on_error=False)
            p = args_to_program(args)
            assert p, 'no program from these arguments!'
            return execute_program(config, p.program, {}, for_visualizer=True)
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
            skip=utils.read_commasep(args.resume_skip),
            drop=utils.read_commasep(args.resume_drop),
        )

    elif p := args_to_program(args):
        if config.name != 'dry-run' and p.doc and not args.yes:
            ATTENTION(p.doc)
        execute_program(config, p.program, p.metadata)

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
        utils.pr(estimates.guesses)

@dataclass(frozen=True)
class Program:
    program: commands.Command
    metadata: dict[str, Any]
    doc: str = ''

def args_to_program(args: Args) -> Program | None:
    v3 = protocol.make_v3(args)

    if args.cell_paint:
        batch_sizes = utils.read_commasep(args.cell_paint, int)
        program = protocol.cell_paint_program(
            batch_sizes=batch_sizes,
            protocol_config=v3,
        )
        return Program(program, {
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
            )
            program = p.make(small_args)
            return Program(program, {'program': p.name}, doc=p.doc)
        else:
            raise ValueError(f'Unknown protocol: {name} (available: {", ".join(small_protocols_dict.keys())})')

    else:
        return None

if __name__ == '__main__':
    main()


