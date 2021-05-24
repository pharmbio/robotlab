from __future__ import annotations

from dataclasses import dataclass, replace, asdict
from typing import *

from datetime import datetime, timedelta

from utils import pr, show
import protocol

from robots import Config, configs
from protocol import Event

import platform
import os
import sys
import json

def execute(events: list[Event], config: Config) -> None:
    metadata = dict(
        experiment_time = str(datetime.now()).split('.')[0],
        host = platform.node(),
        config_name = config.name(),
    )
    log_name = ' '.join(['event log', *metadata.values()])
    log_name = 'logs/' + log_name.replace(' ', '_') + '.json'
    os.makedirs('logs/', exist_ok=True)
    log: list[dict[str, Any]] = []
    for event in events:
        print(event.command)
        start_time = datetime.now()
        event.command.execute(config)
        stop_time = datetime.now()
        entry = dict(
            start_time = str(start_time),
            stop_time = str(stop_time),
            duration=(stop_time - start_time).total_seconds(),
            plate_id=event.plate_id,
            command=event.machine(),
            **asdict(event.command),
        )
        pr(entry)
        entry = {**entry, **metadata}
        log += [entry]
        with open(log_name, 'w') as fp:
            json.dump(log, fp, indent=2)

num_plates = 1

events = protocol.cell_paint_many(num_plates, delay='auto')

config: Config = configs['dry_run']

for arg in sys.argv[1:]:
    arg = arg.replace('-', '_')
    try:
        config = configs[arg]
    except KeyError:
        raise ValueError(f'Unknown config with name {arg}. Available: {show(configs.keys())}')

print(f'Using config =', show(config))

events = protocol.sleek_h21_movements(events)

execute(events, config)

# print('\n'.join(programs.keys()))
