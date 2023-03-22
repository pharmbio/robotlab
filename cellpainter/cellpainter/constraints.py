from __future__ import annotations
from typing import *
from dataclasses import *

from .symbolic import Symbolic
from .commands import (
    Command,
    SeqCmd,
    Fork,
    Meta,
    Checkpoint,
    Duration,
    Idle,

    RobotarmCmd,
    BiotekCmd,
    IncuCmd,
    BlueCmd,
    WaitForCheckpoint,
    Max,
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



from . import estimates
from .estimates import estimate
import pbutils

def optimize(cmd: Command) -> tuple[Command, dict[int, float]]:
    cmd = cmd.make_resource_checkpoints()
    cmd = cmd.align_forks()
    cmd = cmd.assign_ids()
    opt = optimal_env(cmd)
    cmd = cmd.resolve(opt.env)
    return cmd, opt.expected_ends

@dataclass(frozen=True)
class Ids:
    counts: dict[str, int] = field(default_factory=lambda: DefaultDict[str, int](int))

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

    if unsat_core:
        s: Any = Solver()
    else:
        s: Any = Optimize()

    def to_expr(x: Symbolic | float | int | str) -> Any:
        x = Symbolic.wrap(x)
        if use_ints:
            res = round(float(x.offset) * Factor)
            for v in x.var_names:
                vv = Int(v)
                s.add(vv >= 0)
                res += vv
            return res
        else:
            res = round(float(x.offset), Resolution)
            for v in x.var_names:
                vv = Real(v)
                s.add(vv >= 0.0)
                res += vv
            return res

    added = 0

    def max_symbolic(a: Symbolic | float | int, b: Symbolic | float | int, **kws: Any):
        m = Symbolic.var(ids.assign('max'))
        max_a_b, a, b = map(to_expr, (m, a, b))
        if unsat_core:
            print(f'{max_a_b} == max({a}, {b})')
            nonlocal added
            added += 1
            s.assert_and_track(
                And(
                    max_a_b >= a,
                    max_a_b >= b,
                    Or(max_a_b == a, max_a_b == b),
                ),
                f'{max_a_b} == max({a}, {b}) ({added}, {kws})'
            )
        else:
            s.add(max_a_b >= a)
            s.add(max_a_b >= b)
            s.add(Or(max_a_b == a, max_a_b == b))
        return m

    def constrain(lhs: Symbolic | float | int | str, op: Literal['>', '>=', '=='], rhs: Symbolic | float | int | str, **kws: Any):
        match op:
            case '>':
                clause = (to_expr(lhs) > to_expr(rhs))
            case '>=':
                clause = (to_expr(lhs) >= to_expr(rhs))
            case '==':
                clause = (to_expr(lhs) == to_expr(rhs))
            case _: # type: ignore
                raise ValueError(f'{op=} not a valid operator')
        if unsat_core:
            print(f'{lhs} {op} {rhs}')
            if clause == True:
                return
            nonlocal added
            added += 1
            s.assert_and_track(clause, f'{lhs} {op} {rhs} ({added}, {kws})')
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
                constrain(cmd.seconds, '>=', 0, cmd=cmd)
                return begin + cmd.seconds

                return begin
            case RobotarmCmd():
                assert is_main
                return begin + estimate(cmd)
            case BiotekCmd() | IncuCmd() | BlueCmd():
                assert not is_main
                return begin + estimate(cmd)
            case Checkpoint():
                checkpoint = Symbolic.var(cmd.name)
                constrain(begin, '==', checkpoint, cmd=cmd)
                return begin
            case WaitForCheckpoint():
                point = Symbolic.var(cmd.name) + cmd.plus_seconds
                constrain(cmd.plus_seconds, '>=', 0, cmd=cmd)
                if cmd.assume == 'will wait':
                    constrain(point, '>=', begin, cmd=cmd)
                    return point
                elif cmd.assume == 'no wait':
                    constrain(begin, '>=', point, cmd=cmd)
                    return begin
                else:
                    wait_to = Symbolic.var(ids.assign('wait_to'))
                    constrain(wait_to, '==', max_symbolic(point, begin, cmd=cmd), cmd=cmd)
                    return wait_to
            case Duration():
                checkpoint = Symbolic.var(cmd.name)
                constrain(begin, '>=', checkpoint) # checkpoint must have happene, cmd=cmdd
                duration = Symbolic.var(ids.assign(cmd.name + ' duration '))
                constrain(checkpoint + duration, '==', begin, cmd=cmd)
                constrain(duration, '>=', 0, cmd=cmd)
                match cmd.constraint:
                    case Max():
                        maxi = cmd.constraint
                        maximize_terms[maxi.priority].append((maxi.weight, duration))
                    case None:
                        pass
                return begin
            case SeqCmd():
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

    pbutils.pr({
        k: v
        for k, v in env.items()
        if not k.startswith('residue')
    })

    expected_ends = {
        i: model_value(e)
        for i, e in ends.items()
    }

    return OptimalResult(env=env, expected_ends=expected_ends)
