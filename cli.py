from __future__ import annotations
from typing import *
import typing

import argparse
import os
import sys

from runtime import RuntimeConfig, configs, Runtime, config_lookup
from utils import show

import commands
import moves
from moves import movelists
import timings
import protocol
import resume

import utils
from dataclasses import dataclass, field, fields, replace, Field
import json

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

    def parse_args(self, as_type: Type[A], **kws: Any) -> tuple[A, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser(**kws)
        for f in fields(as_type):
            enum = self.enums.get(f)
            name = '--' + f.name.replace('_', '-')
            default = f.default_factory()
            if enum:
                parser.add_argument(name, default=default, help=argparse.SUPPRESS)
                for opt in enum:
                    parser.add_argument('--' + opt.name, dest=f.name, action="store_const", const=opt.value, help=opt.help)
            else:
                f_type = eval(f.type)
                if f_type == list or typing.get_origin(f_type) == list:
                    parser.add_argument(dest=f.name, default=default, nargs="*", help=self.helps.get(f))
                elif f_type == bool:
                    action = 'store_false' if default else 'store_true'
                    parser.add_argument(name, default=bool(default), action=action, help=self.helps.get(f))
                else:
                    parser.add_argument(name, default=default, metavar='X', type=f_type, help=self.helps.get(f))
        v = parser.parse_args()
        return as_type(**v.__dict__), parser

arg = Arg()

@dataclass(frozen=True)
class Args:
    config_name: str = arg(
        'dry-run',
        enum=[option(c.name, c.name, help='Run with config ' + c.name) for c in configs]
    )
    test_comm:                 bool = arg(help=(protocol.test_comm.__doc__ or '').strip())

    cell_paint:                str  = arg(help='Cell paint with batch sizes of BS, separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    incu:                      str  = arg(default='1200,1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    interleave:                bool = arg(help='Interleave plates, required for 7 plate batches')
    two_final_washes:          bool = arg(help='Use two shorter final washes in the end, required for big batch sizes, required for 8 plate batches')
    lockstep:                  bool = arg(help='Allow steps to overlap: first plate PFA starts before last plate Mito finished and so on, required for 10 plate batches')
    log_filename:              str  = arg(help='Manually set the log filename instead of having a generated name based on date')

    test_circuit:              bool = arg(help='Test circuit: start with one plate with lid on incubator transfer door, and all other positions empty!')
    time_bioteks:              bool = arg(help=protocol.time_bioteks)
    time_arm_incu:             bool = arg(help=protocol.time_arm_incu)
    load_incu:                 int  = arg(help=protocol.load_incu)
    unload_incu:               int  = arg(help=protocol.unload_incu)
    lid_stress_test:           bool = arg(help=protocol.lid_stress_test)

    resume:                    str  = arg(help='Resume program given a log file')
    resume_skip:               str  = arg(help='Comma-separated list of simple_id:s to skip (washes and dispenses)')
    resume_drop:               str  = arg(help='Comma-separated list of plate_id:s to drop')

    wash:                      str  = arg(help='Run a program on the washer')
    disp:                      str  = arg(help='Run a program on the dispenser')
    prime:                     str  = arg(help='Run a priming program on the dispenser')
    incu_put:                  str  = arg(help='Put the plate in the transfer station to the argument position POS (L1, .., R1, ..).')
    incu_get:                  str  = arg(help='Get the plate in the argument position POS. It ends up in the transfer station.')

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
            path = getattr(m, '__file__', '')
            if path.startswith(my_dir):
                print(path)
        sys.exit(0)

    config: RuntimeConfig = config_lookup(args.config_name)
    config = config.replace(
        robotarm_speed=args.robotarm_speed,
        log_filename=args.log_filename,
    )

    print('config =', show(config))

    v3 = protocol.make_v3(
        incu_csv=args.incu,
        interleave=args.interleave,
        six=args.two_final_washes,
        lockstep=args.lockstep
    )

    if args.cell_paint:
        batch_sizes = utils.read_commasep(args.cell_paint, int)
        protocol.cell_paint(
            config=config,
            batch_sizes=batch_sizes,
            protocol_config=v3,
        )

    elif args.test_circuit:
        protocol.test_circuit(config=config)

    elif args.time_bioteks:
        protocol.time_bioteks(config=config, protocol_config=v3)

    elif args.time_arm_incu:
        protocol.time_arm_incu(config=config)

    elif args.load_incu:
        protocol.load_incu(config=config, num_plates=args.load_incu)

    elif args.unload_incu:
        protocol.unload_incu(config=config, num_plates=args.unload_incu)

    elif args.lid_stress_test:
        protocol.lid_stress_test(config=config)

    elif args.test_comm:
        protocol.test_comm(config)

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
        protocol.execute_program(config, commands.Sequence(
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
