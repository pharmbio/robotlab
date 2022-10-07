from __future__ import annotations
from dataclasses import dataclass
from pbutils.args import arg, option

from . import execute
from .env import Env

from .protocols import protocols_dict
import pbutils

@dataclass(frozen=True)
class Args:
    num_plates: int       = arg(help='number of plates to work on the hotel (H1,H2,...,H#)')
    hts_file:   str       = arg(help='hts filename on the imx computer')
    thaw_secs:  float     = arg(help='secs the plate goes in RT before imaging')
    params:     list[str] = arg(help='list of barcodes etc')
    speed:      int       = arg(default=20, help='robotarm speed [1..100]')
    live:       bool      = arg(default=False, help='run live (otherwise dry run)')
    keep_going: bool      = arg(default=False, help='work on the queue, keep going even if empty')
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
        if args.keep_going:
            with Env.make(sim=sim) as env:
                execute.execute(env, True)
        else:
            parser.print_help()
    else:
        cmds = p.make(**args.__dict__)
        pbutils.pr(cmds)
        with Env.make(sim=sim) as env:
            execute.enqueue(env, cmds)
            execute.execute(env, False)

if __name__ == '__main__':
    main()
