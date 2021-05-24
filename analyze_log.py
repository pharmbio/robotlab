from typing import *
import json
import sys
from utils import show, pr
import pandas as pd

try:
    logfile = sys.argv[1]
except:
    logfile = './event_log_2021-05-04_19:02:25_live_robotarm_only_one_plate.json'

print(logfile)

df = cast(Any,
    pd.read_json(logfile) #type: ignore
)
df = df.drop(columns='prep est busywait machine'.split())
pr(df)
pr(df.groupby('program_name').duration.describe()[['min', 'mean', 'max']].round(1))
pr(df.groupby(     'command').duration.describe()[['min', 'mean', 'max']].round(1))
