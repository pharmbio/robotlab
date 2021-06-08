from typing import *
import json
import sys
from utils import show, pr
import pandas as pd

try:
    logfile = sys.argv[1]
except:
    logfile = './logs/event_log_2021-06-08_14:03:18_NUC-robotlab_live.json'

print(logfile)

df = cast(Any,
    pd.read_json(logfile) #type: ignore
)
pr(df.columns)
df = df.drop(columns='experiment_time host config_name delay'.split())
pr(df[(df.command == 'wait_for') & (df.base == {'name': 'wash'})])
pr(df[(df.command == 'wash')])

wash_start = df[(df.command == 'wash')].start_time
wash_end   = df[(df.command == 'wait_for') & (df.base == {'name': 'wash'})].stop_time

wash_start = wash_start.reset_index()
wash_end   = wash_end.reset_index()

pr(wash_start)
pr(wash_end)
T = wash_end['stop_time'] - wash_start['start_time']
pr(T[:6].mean())
pr(T[6:].mean())
pr(T[6:].mean() - T[:6].mean())


# pr(df.groupby('program_name').duration.describe()[['min', 'mean', 'max']].round(1))
# pr(df.groupby(     'command').duration.describe()[['min', 'mean', 'max']].round(1))
