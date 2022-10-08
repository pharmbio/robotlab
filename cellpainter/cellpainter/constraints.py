from __future__ import annotations
from typing import *
from dataclasses import *

from .symbolic import Symbolic
from .commands import (
    Command,
    Seq_,
    Fork,
    Meta,
    Checkpoint,
    Duration,
    Idle,
    Info,
    RobotarmCmd,
    BiotekCmd,
    IncuCmd,
    WaitForCheckpoint,
)

def import_z3():
    # z3 messes with the sys.path and writes an error message on stderr, so we silent it here
    import sys
    import contextlib
    import io
    import os
    sys_path0 = [*sys.path]
    tmp = io.StringIO()
    with contextlib.redirect_stderr(tmp):
        import z3 # type: ignore
    if os.environ.get('verbose'):
        print('=== import z3 begin ===')
        print('stderr:', tmp.getvalue())
        print('initial sys.path:', sys_path0)
        print('final sys.path:', sys.path)
        print('=== import z3 end ===')
    sys.path = [*sys_path0]

import_z3()

from z3 import Sum, If, Optimize, Real, Int, Or # type: ignore

from collections import defaultdict

from . import estimates
from .estimates import estimate

def optimize(cmd: Command) -> tuple[Command, dict[str, float]]:
    cmd = cmd.make_resource_checkpoints()
    opt = optimal_env(cmd)
    cmd = cmd.resolve(opt.env)
    return cmd, opt.expected_ends

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

    Resolution = 2

    def to_expr(x: Symbolic | float | int | str) -> Any:
        x = Symbolic.wrap(x)
        s: Any = Sum(*[Real(v) for v in x.var_names]) # type: ignore
        if x.offset:
            offset = round(float(x.offset), Resolution)
            return Sum(offset, s) # type: ignore
        else:
            return s

    s: Any = Optimize()

    def Max(a: Symbolic | float | int, b: Symbolic | float | int):
        m = Symbolic.var(ids.assign('max'))
        max_a_b, a, b = map(to_expr, (m, a, b))
        s.add(max_a_b >= a)
        s.add(max_a_b >= b)
        s.add(Or(max_a_b == a, max_a_b == b))
        return m

    def constrain(lhs: Symbolic | float | int | str, op: Literal['>', '>=', '=='], rhs: Symbolic | float | int | str):
        match op:
            case '>':
                s.add(to_expr(lhs) > to_expr(rhs))
            case '>=':
                s.add(to_expr(lhs) >= to_expr(rhs))
            case '==':
                s.add(to_expr(lhs) == to_expr(rhs))
            case _:
                raise ValueError(f'{op=} not a valid operator')

    maximize_terms: list[tuple[float, Symbolic]] = []
    ends: dict[str, Symbolic] = {}

    def run(cmd: Command, begin: Symbolic, *, is_main: bool) -> Symbolic:
        '''
        returns end
        '''
        match cmd:
            case Idle():
                constrain(cmd.seconds, '>=', 0)
                return begin + cmd.seconds
            case Info():
                return begin
            case RobotarmCmd():
                assert is_main
                return begin + estimate(cmd)
            case BiotekCmd() | IncuCmd():
                assert not is_main
                return begin + estimate(cmd)
            case Checkpoint():
                checkpoint = Symbolic.var(cmd.name)
                constrain(begin, '==', checkpoint)
                return begin
            case WaitForCheckpoint():
                point = Symbolic.var(cmd.name) + cmd.plus_seconds
                constrain(cmd.plus_seconds, '>=', 0)
                if cmd.assume == 'will wait':
                    constrain(point, '>=', begin)
                    return point
                elif cmd.assume == 'no wait':
                    constrain(begin, '>=', point)
                    return begin
                else:
                    wait_to = Symbolic.var(ids.assign('wait_to'))
                    constrain(wait_to, '==', Max(point, begin))
                    return wait_to
            case Duration():
                checkpoint = Symbolic.var(cmd.name)
                constrain(begin, '>=', checkpoint) # checkpoint must have happened
                duration = Symbolic.var(ids.assign(cmd.name + ' duration '))
                constrain(checkpoint + duration, '==', begin)
                constrain(duration, '>=', 0)
                if cmd.exactly is not None:
                    constrain(duration, '==', cmd.exactly)
                if cmd.opt_weight:
                    maximize_terms.append((cmd.opt_weight, duration))
                return begin
            case Seq_():
                end = begin
                for c in cmd.commands:
                    end = run(c, end, is_main=is_main)
                return end
            case Meta():
                end = run(cmd.command, begin, is_main=is_main)
                if cmd_id := cmd.metadata.id:
                    assert isinstance(cmd_id, str)
                    ends[cmd_id] = end
                return end
            case Fork():
                assert is_main, 'can only fork from the main thread'
                _ = run(cmd.command, begin, is_main=False)
                return begin
            case _:
                raise ValueError(type(cmd))

    run(cmd, Symbolic.const(0), is_main=True)

    # batch_sep = 180 # for specs jump
    # constrain('batch sep', '==', batch_sep * 60)

    maximize = Sum(*[  # type: ignore
        coeff * to_expr(v) for coeff, v in maximize_terms
    ])

    if isinstance(maximize, (int, float)):
        pass
    else:
        s.maximize(maximize)

    # print(s)
    check = str(s.check())
    assert check == 'sat', f'Impossible to schedule! (Number of missing time estimates: {len(estimates.guesses)}: {", ".join(str(g) for g in estimates.guesses.keys())}'

    M = s.model()

    def model_value(a: Symbolic | str) -> float:
        s = Symbolic.wrap(a)
        e = to_expr(s)
        if isinstance(e, (float, int)):
            return float(e)
        else:
            # as_decimal result looks like '12.345?'
            return float(M.eval(e).as_decimal(Resolution).strip('?'))

    env = {
        a: model_value(a)
        for a in sorted(variables)
    }

    expected_ends = {
        i: model_value(e)
        for i, e in ends.items()
    }

    return OptimalResult(env=env, expected_ends=expected_ends)
