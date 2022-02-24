from __future__ import annotations
from dataclasses import dataclass
from .utils.args import arg, option

from .scheduler import execute, Env

from .protocols import protocols_dict
from . import utils

import time

@dataclass(frozen=True)
class Args:
    num_plates: int       = arg(help='number of plates to work on the hotel (H1,H2,...,H#)')
    hts_file:   str       = arg(help='hts filename on the imx computer')
    thaw_secs:  float     = arg(help='secs the plate goes in RT before imaging')
    params:     list[str] = arg(help='list of barcodes etc')
    speed: int            = arg(help='robotarm speed [1..100]')
    protocol:   str  = arg(
        enum=[
            option(name, name, help=p.doc)
            for name, p in protocols_dict.items()
        ]
    )

def main():
    args, parser = arg.parse_args(Args, description='Make the lab robots do things.')
    if args.speed:
        with Env().get_robotarm() as arm:
            arm.set_speed(args.speed)
    p = protocols_dict.get(args.protocol)
    if not p:
        parser.print_help()
    else:
        cmds = p.make(**args.__dict__)
        utils.pr(cmds)
        execute(cmds)

if __name__ == '__main__':
    main()
