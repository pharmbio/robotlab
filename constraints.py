from __future__ import annotations
from typing import *
from dataclasses import *

from symbolic import Symbolic
from commands import (
    Command,
    Fork,
    Checkpoint,
    Duration,
    Idle,
    RobotarmCmd,
    BiotekCmd,
    IncuCmd,
    WaitForCheckpoint,
    WaitForResource,
)
from z3 import Sum, If, Optimize, Real, Int # type: ignore

from collections import defaultdict

import utils

@dataclass(frozen=True)
class Ids:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict[str, int](int))

    def next(self, prefix: str = ''):
        self.counts[prefix] += 1
        return prefix + str(self.counts[prefix])

def optimize(cmds: list[Command]) -> tuple[dict[str, float], dict[int, float]]:
    variables: set[str] = {
        v
        for c in cmds
        for v in c.vars_of()
    }
    ids = Ids()

    C: list[
        tuple[Symbolic, Literal['>', '>=', '=='], Symbolic | float | int] |
        tuple[Symbolic, Literal['== max'], Symbolic, Symbolic]
    ] = []

    resource_counters: dict[str, int] = defaultdict(int)
    checkpoints: dict[str, Symbolic] = {}
    checkpoints_referenced: set[str] = set()

    maxi: list[tuple[float, Symbolic]] = []
    last_of_resource: dict[str, Symbolic] = defaultdict(lambda: Symbolic.const(0))

    def run(cmd: Command, begin: Symbolic, *, is_main: bool) -> Symbolic:
        '''
        returns end
        '''
        if isinstance(cmd, RobotarmCmd):
            assert is_main
            return begin + cmd.est()
        elif isinstance(cmd, (BiotekCmd, IncuCmd)):
            if not is_main:
                end = begin + cmd.est()
                return end
            else:
                resource = cmd.required_resource()
                end = begin
                for c in [
                    Fork([cmd], resource=resource),
                    WaitForResource(resource),
                ]:
                    end = run(c, end, is_main=True)
                return end
        elif isinstance(cmd, Checkpoint):
            assert cmd.name not in checkpoints
            checkpoints[cmd.name] = begin
            return begin
        elif isinstance(cmd, WaitForCheckpoint):
            checkpoints_referenced.add(cmd.name)
            point = checkpoints[cmd.name] # Symbolic.var(cmd.name)
            C.append((cmd.plus_seconds, '>=', 0))
            if cmd.flexible:
                wait_to = Symbolic.var(ids.next('wait_to'))
                C.append((wait_to, '== max', point + cmd.plus_seconds, begin))
                return wait_to
            else:
                C.append((point + cmd.plus_seconds, '>=', begin))
                return point + cmd.plus_seconds
        elif isinstance(cmd, Duration):
            # checkpoint must have happened
            checkpoints_referenced.add(cmd.name)
            point = checkpoints[cmd.name]
            duration = Symbolic.var(ids.next(cmd.name + ' duration '))
            C.append((point + duration, '==', begin))
            C.append((duration, '>=', 0))
            if cmd.opt_weight:
                maxi.append((cmd.opt_weight, duration))
            return begin
        elif isinstance(cmd, WaitForResource):
            assert is_main
            wait_to = Symbolic.var(ids.next(f'wait_{cmd.resource}'))
            C.append((wait_to, '== max', last_of_resource[cmd.resource], begin))
            end = wait_to
            return end
        elif isinstance(cmd, Fork):
            assert is_main, 'can only fork from the main thread'

            if cmd.flexible:
                wait_to = Symbolic.var(ids.next(f'wait_{cmd.resource}'))
                C.append((wait_to, '== max', last_of_resource[cmd.resource], begin))
                end = wait_to
            else:
                C.append((begin, '>=', last_of_resource[cmd.resource]))
                end = begin
            for c in cmd.commands:
                end = run(c, end, is_main=False)
            last_of_resource[cmd.resource] = end

            return begin
        else:
            assert isinstance(cmd, Idle)
            C.append((cmd.seconds, '>=', 0))
            return begin + cmd.seconds

    last_main = Symbolic.const(0)

    cmd_ends: dict[int, Symbolic] = {}
    for i, cmd in enumerate(cmds):
        last_main = cmd_ends[i] = run(cmd, last_main, is_main=True)

    unused_checkpoints = checkpoints.keys() - checkpoints_referenced
    if 0 and unused_checkpoints:
        print(f'{unused_checkpoints = }')

    dangling_checkpoints = checkpoints_referenced - checkpoints.keys()
    assert not dangling_checkpoints, f'{dangling_checkpoints = }'



    s: Any = Optimize()

    R = 2

    def to_expr(x: Symbolic | float | int) -> Any:
        x = Symbolic.wrap(x)
        return Sum(
            round(float(x.offset), R),
            *[Real(v) for v in x.var_names]
            # int(x.offset * R),
            # *[Int(v) for v in x.var_names]
        ) # type: ignore

    lc = f'{len(C)=}'

    if 0:
        for c in C:
            print(*c)

        print(lc)

    for i, (lhs, op, *rhss) in enumerate(C):
        # print(i, lhs, op, *rhss)
        rhs, *_ = rhss
        if op == '==':
            s.add(to_expr(lhs) == to_expr(rhs))
        elif op == '>':
            s.add(to_expr(lhs) > to_expr(rhs))
        elif op == '>=':
            s.add(to_expr(lhs) >= to_expr(rhs))
        elif op == '== max':
            a, b = rhss
            s.add(to_expr(lhs) == If(to_expr(a) > to_expr(b), to_expr(a), to_expr(b)))
        else:
            raise ValueError(op)

    # batch_sep = 120 # for v3 jump
    # s.add(Real('batch sep') == batch_sep * 60)

    # maxi = maxi[:1]

    max_v = Sum(*[m * to_expr(v) for m, v in maxi])

    if isinstance(max_v, (int, float)):
        pass
    else:
        s.maximize(max_v)

    if 0:
        for m in maxi:
            print(m)

        print(len(C))

    check = str(s.check())
    # print(check)
    import timings
    assert check == 'sat', timings.Guesses

    M = s.model()

    def get(a: Symbolic | str) -> float:
        s = Symbolic.wrap(a)
        e = to_expr(s)
        if isinstance(e, (float, int)):
            return float(e)
        else:
            return float(M.eval(e).as_decimal(R).strip('?'))

    res = {
        a: get(a)
        for a in sorted(variables)
    }

    # utils.pr(res)

    ends: dict[int, float] = {
        i: get(e)
        for i, e in cmd_ends.items()
    }

    return res, ends


