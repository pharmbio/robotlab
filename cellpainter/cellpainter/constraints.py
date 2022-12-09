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
    Maximize,
    Exactly,
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

from z3 import Sum, If, Optimize, Solver, Real, Int, And, Or # type: ignore

from collections import defaultdict

from . import estimates
from .estimates import estimate
import pbutils

def optimize(cmd: Command) -> tuple[Command, dict[int, float]]:
    cmd = cmd.make_resource_checkpoints()
    cmd = cmd.assign_ids()
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
    expected_ends: dict[int, float]

def optimal_env(cmd: Command, unsat_core: bool=False) -> OptimalResult:
    if unsat_core:
        pbutils.pr(cmd)

    variables = cmd.free_vars()
    ids = Ids()

    Resolution = 4
    Factor = 10 ** Resolution
    use_ints = False

    def to_expr(x: Symbolic | float | int | str) -> Any:
        x = Symbolic.wrap(x)
        if use_ints:
            s: Any = Sum(*[Int(v) for v in x.var_names]) # type: ignore
        else:
            s: Any = Sum(*[Real(v) for v in x.var_names]) # type: ignore
        if x.offset:
            if use_ints:
                offset = round(float(x.offset) * Factor)
            else:
                offset = round(float(x.offset), Resolution)
            return Sum(offset, s) # type: ignore
        else:
            return s

    if unsat_core:
        s: Any = Solver()
    else:
        s: Any = Optimize()

    def Max(a: Symbolic | float | int, b: Symbolic | float | int):
        m = Symbolic.var(ids.assign('max'))
        max_a_b, a, b = map(to_expr, (m, a, b))
        if unsat_core:
            print(f'{max_a_b} == max({a}, {b})')
            s.assert_and_track(
                And(
                    max_a_b >= a,
                    max_a_b >= b,
                    Or(max_a_b == a, max_a_b == b),
                ),
                f'{max_a_b} == max({a}, {b})'
            )
        else:
            s.add(max_a_b >= a)
            s.add(max_a_b >= b)
            s.add(Or(max_a_b == a, max_a_b == b))
        return m

    def constrain(lhs: Symbolic | float | int | str, op: Literal['>', '>=', '=='], rhs: Symbolic | float | int | str):
        match op:
            case '>':
                clause = (to_expr(lhs) > to_expr(rhs))
            case '>=':
                clause = (to_expr(lhs) >= to_expr(rhs))
            case '==':
                clause = (to_expr(lhs) == to_expr(rhs))
            case _:
                raise ValueError(f'{op=} not a valid operator')
        if unsat_core:
            print(f'{lhs} {op} {rhs}')
            if clause == True:
                return
            s.assert_and_track(clause, f'{lhs} {op} {rhs}')
        else:
            s.add(clause)

    maximize_terms: dict[int, list[tuple[float, Symbolic]]] = DefaultDict(list)
    ends: dict[int, Symbolic] = {}

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
                match cmd.constraint:
                    case Exactly():
                        constrain(duration, '==', cmd.constraint.exactly)
                    case Maximize():
                        maxi = cmd.constraint
                        maximize_terms[maxi.priority].append((maxi.weight, duration))
                    case None:
                        pass
                return begin
            case Seq_():
                end = begin
                for c in cmd.commands:
                    end = run(c, end, is_main=is_main)
                return end
            case Meta():
                end = run(cmd.command, begin, is_main=is_main)
                if cmd_id := cmd.metadata.id:
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

    if unsat_core:
        check = str(s.check())
        print(check)
        if check == 'unsat':
            print('unsat core is:')
            print(s.unsat_core())
            raise ValueError(f'Impossible to schedule! (Number of missing time estimates: {len(estimates.guesses)}: {", ".join(str(g) for g in estimates.guesses.keys())}')
        else:
            raise ValueError('Optimization says unsat, but unsat core version says sat')

    # add the constraints with most important first (lexicographic optimization order)
    for _prio, terms in sorted(maximize_terms.items(), reverse=True):
        maximize = Sum(*[  # type: ignore
            coeff * to_expr(v) for coeff, v in terms
        ])
        if isinstance(maximize, (int, float)):
            pass # nothing to do, these were already constants
        else:
            s.maximize(maximize)

    # print(s)
    check = str(s.check())
    if check == 'unsat':
        if 0:
            print('Impossible to schedule, obtaining unsat core')
            optimal_env(cmd, unsat_core=True)
        raise ValueError(f'Impossible to schedule! (Number of missing time estimates: {len(estimates.guesses)}: {", ".join(str(g) for g in estimates.guesses.keys())}')

    M = s.model()

    def model_value(a: Symbolic | str) -> float:
        s = Symbolic.wrap(a)
        e = to_expr(s)
        if isinstance(e, (float, int)):
            if use_ints:
                return float(e) / Factor
            else:
                return float(e)
        else:
            if use_ints:
                return float(M.eval(e).as_long()) / Factor
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
