from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta

from collections import deque
import random

import abc

from robots import *
from moves import *

from utils import pr

@dataclass(frozen=True)
class BfsOpts:
    max_fuel: int=1000
    shuffle_prob: float=0

def bfs_iter(w0: World, opts: BfsOpts=BfsOpts()) -> Iterator[Transition]:
    q: deque[Transition] = deque([Transition(w0)])
    visited: set[str] = set()
    solved: set[str] = set()
    fuel = opts.max_fuel
    while q and fuel > 0:
        fuel -= 1
        if opts.shuffle_prob and random.random() < opts.shuffle_prob:
            random.shuffle(q)
        t = q.popleft()
        w = t.w
        rw = repr(w)
        if rw in visited:
            continue
        visited.add(rw)
        collision = [
            (p, q)
            for p in w.plates.values()
            for q in w.plates.values()
            if p.id < q.id
            if any((
                p.loc == q.loc,
                p.lid_loc != 'self' and p.lid_loc == q.lid_loc,
            ))
        ]
        assert not collision
        for p in w.plates.values():
            if p.waiting_for != 'ready':
                continue
            if not p.queue:
                continue
            if p.id not in solved and (res := p.top().step(p.pop(), w)):
                # keep some slots free for lids and rearranges
                if active_count(res.w) + 3 < len(h_locs):
                    solved.add(p.id)
                    yield replace(t >> res, prio=p.top().prio())
            for res in moves(p, w):
                if res:
                    q.append(t >> res)
    return None

def bfs(w0: World, opts: BfsOpts=BfsOpts()) -> Transition | None:
    first: Transition | None = None
    max_prio = max((0, *(p.top().prio() for p in w0.plates.values() if p.queue)))
    for res in bfs_iter(w0, opts):
        if res.prio == max_prio:
            return res
        if not first:
            first = res
    return first

def execute(w: World, config: Config, shuffle_prob: float=0.0) -> None:

    print('execute', config)

    all_cmds: list[Command] = []

    now = datetime.now()

    while 1:
        print(now.strftime("%Y-%m-%d %H:%M:%S"), *[
            f'{p.loc}{"" if p.waiting_for == "ready" else "*"}'
            for p in w.plates.values()
        ], sep='\t')

        res = bfs(w, BfsOpts(shuffle_prob=shuffle_prob, max_fuel=1000))

        if res:
            w = res.w
            for cmd in res.cmds:
                # print('begin', cmd)
                cmd.execute(config)
                # print('end', cmd)
                all_cmds += [cmd]
                if config.simulate_time:
                    now += timedelta(seconds=10)

        w_start = w

        for p in w.plates.values():
            if p.waiting_for == 'disp':
                if config.disp_mode == 'dry run':
                    w = w.update(p.replace(waiting_for=minutes(5)))
                elif is_ready('disp', config):
                    w = w.update(p.replace(waiting_for='ready'))
            if p.waiting_for == 'wash':
                if config.wash_mode == 'dry run':
                    w = w.update(p.replace(waiting_for=minutes(5)))
                elif is_ready('wash', config):
                    w = w.update(p.replace(waiting_for='ready'))

        if not config.simulate_time:
            now = datetime.now()

        for p in w.plates.values():
            if isinstance(p.waiting_for, timedelta):
                time = now + p.waiting_for
                w = w.update(p.replace(waiting_for=time))

        times: list[datetime] = [
            p.waiting_for
            for p in w.plates.values()
            if isinstance(p.waiting_for, datetime)
        ]

        if config.simulate_time and times and not res:
            now = min(times) # fast forward to the first time

        for p in w.plates.values():
            if isinstance(p.waiting_for, datetime):
                if now >= p.waiting_for:
                    w = w.update(p.replace(waiting_for='ready'))

        any_finished = w_start != w

        if not (times or res or any_finished):
            break


    print('done?')
    print(len(all_cmds))
    pr({
        p.id: (*astuple(p)[:4], len(p.queue))
        for p in w.plates.values()
    })
    # pp(w.plates)
    # pp(world_locations(w))

def execute(events: list[Event], config: Config) -> None:
    for event in events:
        event.execute(config) # some of the execute events are just wait until ready commands
