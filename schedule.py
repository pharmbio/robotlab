from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta

@dataclass(frozen=True)
class Event
    command: Command
    acting_on_plate: str
    begin: float = 0.0
    end: float = 0.0

def to_events(protocol: list[ProtocolStep], plate_id: str, t0=0):
    events: list[Event] = []
    t = t0
    for step in protocol:
        events += [
            Event(
                begin=t,
                end=t + step.est,
                machine=step.machine,
                args=step.args,
            )
        ]
        t += step.est

def resolve_events(events: list[Event]):
    '''
    positions robot_prep in time

    resolves robot coordinates and glues them together?
    '''
    robot_events = sortby(begin, events.proj(robot arm | robot by))
    for r1, r2 in pairwise(robot_events):
        if r2 == robot by:
            assert r1 not robot by, 'cannot have two robot by in a row ???'
            replace r2 with robotarm_move(
                from=end pos of r1
                to=r2 by
                begin=r1.end
                end=some estimate
            )
            # we might get an overlap and check_events will then say that this is infeasible



def check_events(events: list[Event]):
    '''
    checks for overlaps and other inconsistencies which makes a plan infeasible
    '''
    infeasible = []
    foreach machine:
        events = sortby(begin, events.proj(machine))
        for e1, e2 in pairwise(events):
            if e1.end > e2.begin:
                infeasible += [(e1, e2)]

    # could do sanity checks too:
    #   the robot doesn't jump in space
    #   plates and lids never collide
