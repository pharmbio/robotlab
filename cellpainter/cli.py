from __future__ import annotations
from typing import *
import typing

import argparse
import os
import sys
import json
import textwrap
import shlex

from .runtime import RuntimeConfig, configs, config_lookup
from .utils import show
from .moves import movelists

from . import commands
from . import moves
from . import timings
from . import protocol
from . import resume
from .execute import execute_program

from .small_protocols import small_protocols

from . import utils
from dataclasses import dataclass, field, fields, Field, replace

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
            self.helps[f] = help.strip().splitlines()[0]
        if enum:
            self.enums[f] = enum
        return f # type: ignore

    def parse_args(self, as_type: Type[A], args: None | list[str] = None, **kws: Any) -> tuple[A, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser(**kws)
        for f in fields(as_type):
            enum = self.enums.get(f)
            name = '--' + f.name.replace('_', '-')
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
        v = parser.parse_args(args)
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

small_kvs = {p.__name__: p for p in small_protocols}

@dataclass(frozen=True)
class Args:
    config_name: str = arg(
        'dry-run',
        enum=[option(c.name, c.name, help='Run with config ' + c.name) for c in configs]
    )
    test_comm:                 bool = arg(help=protocol.test_comm_program)

    cell_paint:                str  = arg(help='Cell paint with batch sizes of BS, separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    incu:                      str  = arg(default='1200,1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    interleave:                bool = arg(help='Interleave plates, required for 7 plate batches')
    two_final_washes:          bool = arg(help='Use two shorter final washes in the end, required for big batch sizes, required for 8 plate batches')
    lockstep:                  bool = arg(help='Allow steps to overlap: first plate PFA starts before last plate Mito finished and so on, required for 10 plate batches')
    start_from_pfa:            bool = arg(help='Start from PFA (in room temperature). Use this if you have done Mito manually beforehand')
    log_filename:              str  = arg(help='Manually set the log filename instead of having a generated name based on date')
    time_bioteks:              bool = arg(help=protocol.time_bioteks)

    small_protocol:            str  = arg(
        enum=[
            option(name, name, help=(p.__doc__ or '').strip().splitlines()[0])
            for name, p in small_kvs.items()
        ]
    )
    num_plates:                int  = arg(help='For some protocols only: number of plates')

    resume:                    str  = arg(help='Resume program given a log file')
    resume_skip:               str  = arg(help='Comma-separated list of simple_id:s to skip (washes and dispenses)')
    resume_drop:               str  = arg(help='Comma-separated list of plate_id:s to drop')

    wash:                      str  = arg(help='Run a program on the washer')
    disp:                      str  = arg(help='Run a program on the dispenser')
    prime:                     str  = arg(help='Run a priming program on the dispenser')
    incu_put:                  str  = arg(help='Put the plate in the transfer station to the argument position POS (L1, .., R1, ..).')
    incu_get:                  str  = arg(help='Get the plate in the argument position POS. It ends up in the transfer station.')

    visualize:                 bool = arg(help='Run visualizer')

    list_imports:              bool = arg(help='Print the imported python modules for type checking.')

    list_robotarm_programs:    bool = arg(help='List the robot arm programs')
    inspect_robotarm_programs: bool = arg(help='Inspect steps of robotarm programs')
    robotarm:                  bool = arg(help='Run robot arm')
    robotarm_send:             str  = arg(help='Send a raw program to the robot arm')
    robotarm_speed:            int  = arg(default=100, help='Robot arm speed [1-100]')
    program_names:             list[str] = arg(help='Robot arm program name to run')
    json_arg:                  str  = arg(help='Give arguments as json on the command line')

def main():
    args, parser = arg.parse_args(Args, description='Make the lab robots do things.')
    if args.json_arg:
        args = Args(**json.loads(args.json_arg))

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

    v3 = protocol.make_v3(args)

    if args.visualize:
        from . import protocol_vis as pv
        cmdname, *argv = [arg for arg in sys.argv if not arg.startswith('--vi')]
        cmdline = shlex.join(argv)
        def cmdline_to_events(cmdline: str):
            args, _ = arg.parse_args(Args, args=[cmdname, *shlex.split(cmdline)])
            p = args_to_program(args)
            assert p
            return execute_program(config, p.program, {}, for_visualizer=True)
        pv.start(cmdline, cmdline_to_events)

    elif p := args_to_program(args):
        if config.name != 'dry-run' and p.doc:
            ATTENTION(p.doc)
        execute_program(config, p.program, p.metadata)

    elif args.robotarm:
        runtime = config.make_runtime()
        for name in args.program_names:
            if name in movelists:
                commands.RobotarmCmd(name).execute(runtime, {})
            else:
                raise ValueError(f'Unknown program: {name}')

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
            import re
            m = re.search(r'\d+', k)
            if not m or m.group(0) in {"19", "21"}:
                import textwrap
                print()
                print(k + ':\n' + textwrap.indent(v.describe(), '  '))

    elif args.wash:
        runtime = config.make_runtime()
        path = v3.wash[int(args.wash)]
        assert path, utils.pr(v3.wash)
        return Program(commands.Sequence(
            commands.WashCmd(path, cmd='Validate'),
            commands.WashCmd(path, cmd='RunValidated'),
        ), {'program': 'wash'})

    elif args.disp:
        runtime = config.make_runtime()
        path = v3.disp[int(args.disp)]
        assert path, utils.pr(v3.disp)
        commands.DispCmd(path).execute(runtime, {})

    elif args.prime:
        runtime = config.make_runtime()
        path = v3.prime[int(args.prime)]
        assert path, utils.pr(v3.prime)
        commands.DispCmd(path).execute(runtime, {})

    elif args.incu_put:
        runtime = config.make_runtime()
        commands.IncuCmd('put', args.incu_put).execute(runtime, {})

    elif args.incu_get:
        runtime = config.make_runtime()
        commands.IncuCmd('get', args.incu_get).execute(runtime, {})

    elif args.resume:
        resume.resume_program(
            config,
            args.resume,
            skip=utils.read_commasep(args.resume_skip),
            drop=utils.read_commasep(args.resume_drop),
        )

    else:
        parser.print_help()

    if timings.Guesses:
        print('Guessed these times:')
        utils.pr(timings.Guesses)

if __name__ == '__main__':
    main()

@dataclass(frozen=True)
class Program:
    program: commands.Command
    metadata: dict[str, Any]
    doc: str | None = None

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

    elif args.time_bioteks:
        program = protocol.time_bioteks(protocol_config=v3)
        return Program(program, {'program': 'time_bioteks'}, doc=protocol.time_bioteks.__doc__)

    elif args.test_comm:
        program = protocol.test_comm_program()
        return Program(program, {'program': 'test_comm'}, doc=protocol.test_comm_program.__doc__)

    elif args.small_protocol:
        name = args.small_protocol.replace('-', '_')
        p = small_kvs.get(name)
        if p:
            program = p(args)
            return Program(program, {'program': p.__name__}, doc=p.__doc__)
        else:
            raise ValueError(f'Unknown protocol: {name} (available: {", ".join(p.__name__ for p in small_protocols)})')

    elif args.wash:
        path = v3.wash[int(args.wash)]
        assert path, utils.pr(v3.wash)
        return Program(commands.Sequence(
            commands.WashCmd(path, cmd='Validate'),
            commands.WashCmd(path, cmd='RunValidated'),
        ), {'program': 'wash'})

    else:
        return None

if __name__ == '__main__':
    main()
