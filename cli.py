from __future__ import annotations
from typing import *

import argparse

from robots import Config, configs
from utils import show

import robots
import moves
from moves import movelists

import protocol

def main():
    parser = argparse.ArgumentParser(description='Make the lab robots do things.', )
    parser.add_argument('--config', metavar='NAME', type=str, default='dry-run', help='Config to use')
    for k, v in configs.items():
        parser.add_argument('--' + k, dest="config", action="store_const", const=k, help='Run with config ' + k)

    parser.add_argument('--cell-paint', metavar='BS', type=int, default=None, help='Cell paint with a batch size of BS. Plates stored in L1, L2, ..')
    parser.add_argument('--num-batches', metavar='N', type=int, default=1, help='Number of batches to use when cell painting')
    parser.add_argument('--between-batch-delay', metavar='T', type=str, default='auto', help='Delay between batches in seconds (or the default: "auto")')
    parser.add_argument('--within-batch-delay',  metavar='T', type=str, default='auto', help='Delay within batches in seconds (or the default: "auto")')
    parser.add_argument('--test-circuit', action='store_true', help='Test with a circuit protocol which returns plates back into the incubator')

    parser.add_argument('--wash', action='store_true', help='Run a (fixed) test program on the washer')
    parser.add_argument('--disp', action='store_true', help='Run a (fixed) test program on the dispenser')
    parser.add_argument('--incu-put', metavar='POS', type=str, default=None, help='Put the plate in the transfer station to the argument position POS (L1, .., R1, ..).')
    parser.add_argument('--incu-get', metavar='POS', type=str, default=None, help='Get the plate in the argument position POS. It ends up in the transfer station.')

    parser.add_argument('--list-robotarm-programs', action='store_true', help='List the robot arm programs')
    parser.add_argument('--inspect-robotarm-programs', action='store_true', help='Inspect steps of robotarm programs')
    parser.add_argument('--robotarm', action='store_true', help='Run robot arm')
    parser.add_argument('--robotarm-send', metavar='STR', type=str, help='Send a raw program to the robot arm')
    parser.add_argument('--robotarm-speed', metavar='N', type=int, default=100, help='Robot arm speed [1-100]')
    parser.add_argument('program_name', type=str, nargs='*', help='Robot arm program name to run')

    args = parser.parse_args()
    print(f'args =', show(args.__dict__))

    config_name = args.config
    try:
        config: Config = configs[config_name]
    except KeyError:
        raise ValueError(f'Unknown {config_name = }. Available: {show(configs.keys())}')

    print(f'Using config =', show(config))

    if args.cell_paint:
        robots.get_robotarm(config).set_speed(args.robotarm_speed).close()
        protocol.main(
            num_batches=args.num_batches,
            batch_size=args.cell_paint,
            between_batch_delay_str=args.between_batch_delay,
            within_batch_delay_str=args.within_batch_delay,
            config=config,
            test_circuit=args.test_circuit
        )

    elif args.robotarm:
        robots.get_robotarm(config).set_speed(args.robotarm_speed).close()
        for name in args.program_name:
            if name in movelists:
                robots.robotarm_cmd(name).execute(config)
            else:
                print('Unknown program:', name)

    elif args.robotarm_send:
        arm = robots.get_robotarm(config)
        arm.set_speed(args.robotarm_speed)
        arm.execute_moves([moves.RawCode(args.robotarm_send)], name='raw')
        arm.close()

    elif args.list_robotarm_programs:

        for name in movelists.keys():
            print(name)

    elif args.inspect_robotarm_programs:
        events, _, _ = protocol.cell_paint_batches_auto_delay(1, 2, test_circuit=True)
        events = protocol.sleek_movements(events)

        for k, v in movelists.items():
            import re
            m = re.search(r'\d+', k)
            if not m or m.group(0) in {"19", "21"}:
                import textwrap
                print()
                print(k + ':\n' + textwrap.indent(v.describe(), '  '))

    elif args.wash:
        robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=0).execute(config)
        robots.wait_for_ready_cmd('wash').execute(config)

    elif args.disp:
        robots.disp_cmd('automation/1_D_P1_30ul_mito.LHC', disp_pump='P1', est=0).execute(config)
        robots.wait_for_ready_cmd('disp').execute(config)

    elif args.incu_put:
        robots.incu_cmd('put', args.incu_put, est=0).execute(config)
        robots.wait_for_ready_cmd('incu').execute(config)

    elif args.incu_get:
        robots.incu_cmd('get', args.incu_get, est=0).execute(config)
        robots.wait_for_ready_cmd('incu').execute(config)

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
