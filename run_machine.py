from __future__ import annotations
from typing import *

from utils import *
from robots import *

config = configs['live_execute_all']

print(f'Using config =', show(config))

if '--wash' in sys.argv:
    wash_cmd('automation/2_4_6_W-3X_FinalAspirate.LHC', est=0).execute(config)

if '--disp' in sys.argv:
    disp_cmd('automation/1_D_P1_30ul_mito.LHC', est=0).execute(config)

