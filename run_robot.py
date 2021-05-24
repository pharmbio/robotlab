from __future__ import annotations

from typing import *

from utils import *
from robots import *

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

    get_robotarm(config).set_speed(80).close()

    for name in sys.argv:
        if name in movelists:
            robotarm_cmd(name).execute(config)

