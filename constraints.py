from __future__ import annotations
from typing import *
from dataclasses import *

from symbolic import Symbolic
import commands
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
from z3 import Sum, If, Optimize, Real, Int, Or # type: ignore

from collections import defaultdict

import utils

@dataclass(frozen=True)
class Ids:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict[str, int](int))

    def assign(self, prefix: str = ''):
        self.counts[prefix] += 1
        return prefix + str(self.counts[prefix])

def optimize(cmds: list[Command]) -> tuple[dict[str, float], dict[int, float]]:
    variables = commands.FreeVars(cmds)
    ids = Ids()

    R = 2
    def to_expr(x: Symbolic | float | int) -> Any:
        x = Symbolic.wrap(x)
        return Sum(
            round(float(x.offset), R),
            *[Real(v) for v in x.var_names]
            # int(x.offset * R),
            # *[Int(v) for v in x.var_names]
        ) # type: ignore

    s: Any = Optimize()

    C: list[Any] = []

    def Max(a: Symbolic | float | int, b: Symbolic | float | int):
        m = Symbolic.var(ids.assign('max'))
        max_a_b, a, b = map(to_expr, (m, a, b))
        s.add(max_a_b >= a)
        s.add(max_a_b >= b)
        s.add(Or(max_a_b == a, max_a_b == b))
        return m

    def constrain(lhs: Symbolic, op: Literal['>', '>=', '==', '== max'], rhs: Symbolic | float | int, rhs2: Symbolic | None = None):
        match op:
            case '>':
                s.add(to_expr(lhs) > to_expr(rhs))
            case '>=':
                s.add(to_expr(lhs) >= to_expr(rhs))
            case '==':
                s.add(to_expr(lhs) == to_expr(rhs))
            case _:
                raise ValueError(f'{op=} not a valid operator')

        C.append((lhs, op, rhs))

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
            constrain(cmd.plus_seconds, '>=', 0)
            wait_to = Symbolic.var(ids.assign('wait_to'))
            if not cmd.flexible:
                constrain(wait_to, '==', point + cmd.plus_seconds)
            constrain(wait_to, '==', Max(point + cmd.plus_seconds, begin))
            return wait_to
        elif isinstance(cmd, Duration):
            # checkpoint must have happened
            checkpoints_referenced.add(cmd.name)
            point = checkpoints[cmd.name]
            duration = Symbolic.var(ids.assign(cmd.name + ' duration '))
            constrain(point + duration, '==', begin)
            constrain(duration, '>=', 0)
            if cmd.opt_weight:
                maxi.append((cmd.opt_weight, duration))
            return begin
        elif isinstance(cmd, WaitForResource):
            assert is_main
            wait_to = Symbolic.var(ids.assign(f'wait_{cmd.resource}'))
            constrain(wait_to, '==', Max(last_of_resource[cmd.resource], begin))
            end = wait_to
            return end
        elif isinstance(cmd, Fork):
            assert is_main, 'can only fork from the main thread'

            wait_to = Symbolic.var(ids.assign(f'wait_{cmd.resource}'))
            if not cmd.flexible:
                constrain(wait_to, '==', begin)
            constrain(wait_to, '==', Max(last_of_resource[cmd.resource], begin))
            end = wait_to
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

    lc = f'{len(C)=}'

    if 0:
        for c in C:
            print(*c)

        print(lc)

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


