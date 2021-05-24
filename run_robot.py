from __future__ import annotations

from typing import *

from utils import show
from robots import Config, configs
import robots

from moves import movelists

import sys

if '--list-programs' in sys.argv:
    for name in movelists.keys():
        print(name)

else:
    config = configs['live_robotarm_only']
    if '--no-gripper' in sys.argv:
        config = configs['live_robotarm_no_gripper']

    print(f'Using config =', show(config))

    robots.get_robotarm(config).set_speed(80).close()

    for name in sys.argv:
        if name in movelists:
            robots.robotarm_cmd(name).execute(config)

