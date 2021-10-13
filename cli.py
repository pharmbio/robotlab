from __future__ import annotations
from typing import *

import argparse

from runtime import RuntimeConfig, configs, get_robotarm, Runtime
from utils import show

import commands
import moves
from moves import movelists
import timings

import utils

import protocol

def main():
    parser = argparse.ArgumentParser(description='Make the lab robots do things.', )
    parser.add_argument('--config', metavar='NAME', type=str, default='dry-run', help=argparse.SUPPRESS)
    for k, v in configs.items():
        parser.add_argument('--' + k, dest="config", action="store_const", const=k, help='Run with config ' + k)

    parser.add_argument('--test-comm', action='store_true', help=(protocol.test_comm.__doc__ or '').strip())

    parser.add_argument('--cell-paint', metavar='BS', type=str, default=None, help='Cell paint with batch sizes of BS, separated by comma (such as 6,6 for 2x6). Plates start stored in incubator L1, L2, ..')
    parser.add_argument('--incu', metavar='IS', type=str, default='1200,1200,1200,1200', help='Incubation times in seconds, separated by comma')
    parser.add_argument('--interleave', action='store_true', help='Interleave plates, required for batch sizes of more than 6 plates')
    parser.add_argument('--test-circuit', action='store_true', help='Test circuit: start with one plate with lid on incubator transfer door, and all other positions empty!')
    parser.add_argument('--time-bioteks', action='store_true', help=(protocol.time_bioteks.__doc__ or '').strip().splitlines()[0])
    parser.add_argument('--time-arm-incu', action='store_true', help=(protocol.time_arm_incu.__doc__ or '').strip().splitlines()[0])
    parser.add_argument('--load-incu', type=int, help=(protocol.load_incu.__doc__ or '').strip().splitlines()[0])
    parser.add_argument('--unload-incu', type=int, help=(protocol.unload_incu.__doc__ or '').strip().splitlines()[0])
    parser.add_argument('--lid-stress-test', action='store_true', help=(protocol.lid_stress_test.__doc__ or '').strip().splitlines()[0])

    parser.add_argument('--wash', type=str, help='Run a program on the washer')
    parser.add_argument('--disp', type=str, help='Run a program on the dispenser')
    parser.add_argument('--prime', type=str, help='Run a priming program on the dispenser')
    parser.add_argument('--incu-put', metavar='POS', type=str, default=None, help='Put the plate in the transfer station to the argument position POS (L1, .., R1, ..).')
    parser.add_argument('--incu-get', metavar='POS', type=str, default=None, help='Get the plate in the argument position POS. It ends up in the transfer station.')

    parser.add_argument('--list-robotarm-programs', action='store_true', help='List the robot arm programs')
    parser.add_argument('--inspect-robotarm-programs', action='store_true', help='Inspect steps of robotarm programs')
    parser.add_argument('--robotarm', action='store_true', help='Run robot arm')
    parser.add_argument('--robotarm-send', metavar='STR', type=str, help='Send a raw program to the robot arm')
    parser.add_argument('--robotarm-speed', metavar='N', type=int, default=100, help='Robot arm speed [1-100]')
    parser.add_argument('program_name', type=str, nargs='*', help='Robot arm program name to run')

    args = parser.parse_args()
    if 0:
        print(f'args =', show(args.__dict__))

    config_name = args.config
    try:
        config: RuntimeConfig = configs[config_name]
    except KeyError:
        raise ValueError(f'Unknown {config_name = }. Available: {show(configs.keys())}')

    config = config.with_speed(args.robotarm_speed)

    print(f'Using', config.name(), 'config =', show(config))

    v3 = protocol.make_v3(incu_csv=args.incu, linear=not args.interleave)

    if args.cell_paint:
        batch_sizes: list[int] = [
            int(bs.strip())
            for bs in args.cell_paint.split(',')
        ]
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
        runtime = Runtime(config)
        for name in args.program_name:
            if name in movelists:
                commands.RobotarmCmd(name).execute(runtime, {})
            else:
                raise ValueError(f'Unknown program: {name}')

    elif args.robotarm_send:
        runtime = Runtime(config)
        arm = runtime.get_robotarm()
        arm.execute_moves([moves.RawCode(args.robotarm_send)], name='raw')
        arm.close()

    elif args.list_robotarm_programs:
        for name in movelists.keys():
            print(name)

    elif args.inspect_robotarm_programs:
        events = protocol.paint_batch(protocol.define_plates([6, 6]), protocol_config=v3)

        for k, v in movelists.items():
            import re
            m = re.search(r'\d+', k)
            if not m or m.group(0) in {"19", "21"}:
                import textwrap
                print()
                print(k + ':\n' + textwrap.indent(v.describe(), '  '))

    elif args.wash:
        runtime = Runtime(config)
        path = getattr(v3.wash, args.wash, None)
        assert path, utils.pr(v3.wash)
        protocol.execute_commands(config, [
            commands.WashCmd(path, cmd='Validate'),
            commands.WashCmd(path, cmd='RunValidated'),
        ], {'program': 'wash'})

    elif args.disp:
        runtime = Runtime(config)
        path = getattr(v3.disp, args.disp, None)
        assert path, utils.pr(v3.disp)
        commands.DispCmd(path).execute(runtime, {})

    elif args.prime:
        runtime = Runtime(config)
        path = getattr(v3.prime, args.prime, None)
        assert path, utils.pr(v3.prime)
        commands.DispCmd(path).execute(runtime, {})

    elif args.incu_put:
        runtime = Runtime(config)
        commands.IncuCmd('put', args.incu_put).execute(runtime, {})

    elif args.incu_get:
        runtime = Runtime(config)
        commands.IncuCmd('get', args.incu_get).execute(runtime, {})

    else:
        parser.print_help()

    if timings.Guesses:
        print('Guessed these times:')
        utils.pr(timings.Guesses)

if __name__ == '__main__':
    main()
