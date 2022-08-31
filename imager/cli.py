from __future__ import annotations
from dataclasses import dataclass
from .utils.args import arg, option

from .scheduler import execute, Env
from . import scheduler

from .protocols import protocols_dict
from . import utils

import time

@dataclass(frozen=True)
class Args:
    num_plates: int       = arg(help='number of plates to work on the hotel (H1,H2,...,H#)')
    hts_file:   str       = arg(help='hts filename on the imx computer')
    thaw_secs:  float     = arg(help='secs the plate goes in RT before imaging')
    params:     list[str] = arg(help='list of barcodes etc')
    speed:      int       = arg(default=20, help='robotarm speed [1..100]')
    live:       bool      = arg(default=False, help='run live (otherwise dry run)')
    protocol:   str  = arg(
        enum=[
            option(name, name, help=p.doc)
            for name, p in protocols_dict.items()
        ]
    )

def main():
    args, parser = arg.parse_args(Args, description='Make the lab robots do things.')
    sim = not args.live
    if args.speed:
        with Env.make(sim=sim) as env:
            with env.get_robotarm() as arm:
                arm.set_speed(args.speed)
    p = protocols_dict.get(args.protocol)
    if not p:
        parser.print_help()
    else:
        cmds = p.make(**args.__dict__)
        utils.pr(cmds)
        with Env.make(sim=sim) as env:
            scheduler.enqueue(env, cmds)
            scheduler.execute(env)

if __name__ == '__main__':
    main()
