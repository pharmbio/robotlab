from __future__ import annotations
from typing import *

import sys

from utils import show, pr
from robots import Config, configs
import robots

config = configs['live_execute_all']

print(f'Using config =', show(config))

args = dict(enumerate(sys.argv[1:]))

if args.get(0) == '--wash':
    robots.wash_cmd('automation/2_4_6_W-3X_FinalAspirate_test.LHC', est=0).execute(config)
    robots.wait_for_ready_cmd('wash').execute(config)

if args.get(0) == '--disp':
    robots.disp_cmd('automation/1_D_P1_30ul_mito.LHC', est=0).execute(config)
    robots.wait_for_ready_cmd('disp').execute(config)

if args.get(0) == '--incu-put':
    robots.incu_cmd('put', args[1], est=0).execute(config)
    robots.wait_for_ready_cmd('incu').execute(config)

if args.get(0) == '--incu-get':
    robots.incu_cmd('get', args[1], est=0).execute(config)
    robots.wait_for_ready_cmd('incu').execute(config)

