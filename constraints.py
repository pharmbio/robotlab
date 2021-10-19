from __future__ import annotations
from typing import *
from dataclasses import *

from symbolic import Symbolic
import commands
from commands import (
    Command,
    Seq,
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

def optimize(cmd: Command) -> tuple[Command, dict[str, float]]:
    cmd = cmd.make_resource_checkpoints()
    env = optimal_env(cmd)
    cmd = cmd.resolve(env.env)
    return cmd, env.expected_ends

@dataclass(frozen=True)
class Ids:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict[str, int](int))

    def assign(self, prefix: str = ''):
        self.counts[prefix] += 1
        return prefix + str(self.counts[prefix])

@dataclass(frozen=True)
class OptimalResult:
    env: dict[str, float]
    expected_ends: dict[str, float]

def optimal_env(cmd: Command) -> OptimalResult:
    variables = cmd.free_vars()
    ids = Ids()

    R = 2
    def to_expr(x: Symbolic | float | int | str) -> Any:
        x = Symbolic.wrap(x)
        if x.offset:
            return Sum(
                round(float(x.offset), R),
                *[Real(v) for v in x.var_names]
                # int(x.offset * R),
                # *[Int(v) for v in x.var_names]
            ) # type: ignore
        else:
            return Sum(*[Real(v) for v in x.var_names]) # type: ignore

    s: Any = Optimize()

    C: list[Any] = []

    def Max(a: Symbolic | float | int, b: Symbolic | float | int):
        m = Symbolic.var(ids.assign('max'))
        max_a_b, a, b = map(to_expr, (m, a, b))
        s.add(max_a_b >= a)
        s.add(max_a_b >= b)
        s.add(Or(max_a_b == a, max_a_b == b))
        return m

    def constrain(lhs: Symbolic | str, op: Literal['>', '>=', '=='], rhs: Symbolic | float | int | str):
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

    checkpoints: dict[str, Symbolic] = {}
    checkpoints_referenced: set[str] = set()

    maxi: list[tuple[float, Symbolic]] = []
    expected_ends: dict[str, Symbolic] = {}

    def run(cmd: Command, begin: Symbolic, *, is_main: bool) -> Symbolic:
        end = run_inner(cmd, begin, is_main=is_main)
        match cmd:
            case Seq() if cmd_id := cmd.metadata.get('id'):
                assert isinstance(cmd_id, str)
                expected_ends[cmd_id] = end
        return end

    def run_inner(cmd: Command, begin: Symbolic, *, is_main: bool) -> Symbolic:
        '''
        returns end
        '''
        match cmd:
            case Idle():
                C.append((cmd.seconds, '>=', 0))
                return begin + cmd.seconds
            case RobotarmCmd():
                assert is_main
                return begin + cmd.est()
            case BiotekCmd() | IncuCmd():
                assert not is_main
                return begin + cmd.est()
            case Checkpoint():
                assert cmd.name not in checkpoints
                checkpoints[cmd.name] = Symbolic.var(cmd.name)
                constrain(begin, '==', checkpoints[cmd.name])
                return begin
            case WaitForCheckpoint():
                point = checkpoints[cmd.name]
                constrain(cmd.plus_seconds, '>=', 0)
                if cmd.assume == 'will wait':
                    constrain(point + cmd.plus_seconds, '>=', begin)
                    return point + cmd.plus_seconds
                elif cmd.assume == 'no wait':
                    constrain(begin, '>=', point + cmd.plus_seconds)
                    return begin
                else:
                    wait_to = Symbolic.var(ids.assign('wait_to'))
                    constrain(wait_to, '==', Max(point + cmd.plus_seconds, begin))
                    return wait_to
            case Duration():
                # checkpoint must have happened
                point = checkpoints[cmd.name]
                duration = Symbolic.var(ids.assign(cmd.name + ' duration '))
                constrain(point + duration, '==', begin)
                constrain(duration, '>=', 0)
                if cmd.exactly is not None:
                    constrain(duration, '==', cmd.exactly)
                if cmd.opt_weight:
                    maxi.append((cmd.opt_weight, duration))
                return begin
            case Seq():
                end = begin
                for c in cmd.commands:
                    end = run(c, end, is_main=is_main)
                return end
            case Fork():
                assert is_main, 'can only fork from the main thread'
                _ = run(cmd.command, begin, is_main=False)
                return begin
            case _:
                raise ValueError(type(cmd))

    run(cmd, Symbolic.const(0), is_main=True)

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

    print(s)
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

    env = {
        a: get(a)
        for a in sorted(variables)
    }

    # utils.pr(env)

    ends: dict[str, float] = {
        i: get(e)
        for i, e in expected_ends.items()
    }

    return OptimalResult(env=env, expected_ends=ends)


