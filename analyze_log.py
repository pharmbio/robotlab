from typing import *
import json
import sys
from utils import show, pr
import pandas as pd
from datetime import datetime, timedelta

import datetime
import sqlite3

def load(logfile: str):
    db = sqlite3.connect(':memory:')
    db.row_factory=lambda c, r: dict(sqlite3.Row(c, r)) #type: ignore
    df = cast(pd.DataFrame,
        pd.read_json(logfile, lines=True) #type: ignore
    )
    df.to_sql(con=db, name='log') #type: ignore
    return db, df

def migrate(logfile: str, outfile: str):
    db, df = load(logfile)
    dicts = pr(list(db.execute('''
        select
            b.log_time,
            round(86400 * (julianday(b.log_time) - julianday(a.experiment_time)), 3) as t,
            round(86400 * (julianday(a.log_time) - julianday(a.experiment_time)), 3) as t0,
            round(86400 * (julianday(b.log_time) - julianday(a.log_time)), 3) as duration,
            'end' as kind,
            a.source,
            a.arg,
            a.event_id,
            a.event_plate_id,
            a.event_part,
            a.event_subpart,
            a.event_id || '_' || a.source as id
        from log a, log b
        where a.event_id = b.event_id
        and a.source = b.source
        and a.kind = "start"
        and b.kind = "stop"
    ''')))
    with open(outfile, 'w') as fp:
        print('\n'.join(json.dumps(d) for d in dicts), file=fp)

def main(logfile: str):
    db, df = load(logfile)

    df = cast(Any, df)
    df = df[df.kind == 'end']
    df = df.drop(columns=['log_time', 'kind', 'event_id'])
    if 'id' in df.columns:
        df = df.drop(columns=['id'])
    df = df[~df.arg.str.contains('PRIME')]
    df = df.rename(columns={'event_plate_id': 'plate'})
    df = df.rename(columns={'source': 'title'})

    derived: list[dict[str, Any]] = []

    for plate in df.plate.unique():
        dfp = df[df.plate == plate]

        wash_disp = dfp[dfp.title.eq('disp') | dfp.title.eq('wash')]
        for i in range(len(wash_disp) - 1):
            a = wash_disp.iloc[i]
            b = wash_disp.iloc[i+1]
            if a.title == 'disp' or b.title == 'wash':
                title = 'incubation'
            else:
                title = 'wash to disp'
            t0 = a.t
            t = b.t0
            entry = {
                'plate': plate,
                'event_part': a.event_part,
                't': t,
                't0': t0,
                'duration': t - t0,
                'title': title,
                'include': True,
            }
            derived += [entry]

        lids = dfp[dfp.arg.str.contains('lid')]
        for i in range(len(lids) - 1):
            a = lids.iloc[i]
            b = lids.iloc[i+1]
            t0 = a.t
            t = b.t0
            if 'put' in a.arg:
                title = 'without lid'
                continue
            else:
                title = 'with lid'
            entry = {
                'plate': plate,
                'event_part': a.event_part,
                't': t,
                't0': t0,
                'duration': t - t0,
                'title': title,
                'include': True,
            }
            derived += [entry]

        incu = dfp[dfp.arg.str.contains('incu') & dfp.title.eq('wait')]
        for i in range(len(incu) - 1):
            a = incu.iloc[i]
            b = incu.iloc[i+1]
            if 'to incu' in a.event_subpart:
                title = 'in 37°'
            else:
                continue
            t0 = a.t
            t = b.t0
            entry = {
                'plate': plate,
                'event_part': a.event_part,
                't': t,
                't0': t0,
                'duration': t - t0,
                'title': title,
                'include': True,
            }
            derived += [entry]

    df = df.append(derived)
    df = df[(df.include == True) | (df.title == 'wash') | (df.title == 'disp')]
    df = df.sort_values('t0')
    df = df.drop(columns=['arg', 'event_subpart', 'include', 't', 't0'])
    df = df.reset_index(drop=True)
    df.duration = round(df.duration, 1)
    df.plate = df.plate.str[1:].str.lstrip('0')

    for title in df.title.unique():
        p = df[df.title == title]
        p = p.reset_index(drop=True)
        pr(p[['event_part', 'plate', 'duration', 'title']])

0 and migrate(
    './logs/event_log_2021-06-09_09:25:03_NUC-robotlab_live.jsonl',
    './logs/event_log_2021-06-09_09:25:03_6,6_live.jsonl',
)

if __name__ == '__main__':
    logfile = sys.argv[1]
    main(logfile)

