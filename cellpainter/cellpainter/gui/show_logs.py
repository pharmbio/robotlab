from __future__ import annotations
from typing import *
from dataclasses import *

from viable import store, js, call, Serve, Flask, Int, Str, Bool
from viable import Tag, div, span, label, button, pre
import viable as V

from datetime import datetime, timedelta
from pathlib import Path

from ..log import ExperimentMetadata, Log
from ..commands import ProgramMetadata

from .db_edit import Edit
from . import common

A = TypeVar('A')
B = TypeVar('B')
class dotdict(Generic[A, B], dict[A, B]):
    __getattr__ = dict.__getitem__ # type: ignore
    __setattr__ = dict.__setitem__ # type: ignore
    __delattr__ = dict.__delitem__ # type: ignore

def show_logs() -> Iterator[Tag | V.Node | dict[str, str]]:
    enable_edit = store.bool()
    echo = store.bool(default=False)
    show_protocol_dir = store.str(default='')
    store.assign_names(locals())
    tabindexes: Any = {}
    logs: list[dict[str, Any]] = []
    for log in sorted(Path('logs').glob('*.db')):
        if 1 and 'simulate' in str(log):
            continue
        row: dict[str, Any] = dotdict()
        try:
            g = Log.connect(log)
            # g.make_zipfile()
            pm = g.program_metadata() or ProgramMetadata().save(g.db)
            em = g.experiment_metadata() or ExperimentMetadata().save(g.db)
            edit_em = Edit(log, em, tabindexes=tabindexes, enable_edit=enable_edit.value, echo=echo.value)
            edit_em = Edit(log, em, tabindexes=tabindexes, enable_edit=enable_edit.value, echo=echo.value)
            edit_pm = Edit(log, pm, tabindexes=tabindexes, enable_edit=enable_edit.value, echo=echo.value)
            if (rt := g.runtime_metadata()):
                row.wkd = rt.start_time.strftime('%a')
                row.datetime = rt.start_time.strftime('%Y-%m-%d %H:%M') + '-' + (rt.start_time + timedelta(seconds=g.time_end(only_completed=True))).strftime('%H:%M')
                row.desc = edit_em(edit_em.attr.desc)
                row.operators = edit_em(edit_em.attr.operators)
                row.plates = edit_pm(edit_pm.attr.num_plates, int, enable_edit=False).extend(class_='right')
                # row.batch_sizes = edit_pm(edit_pm.attr.batch_sizes, int, enable_edit=False).extend(class_='right')
                if rt.config_name != 'live':
                    row.live = rt.config_name
                    continue
                if pm.protocol != 'cell-paint':
                    row.protocol = edit_pm(edit_pm.attr.protocol, enable_edit=False)
                row.from_stage = edit_pm(edit_pm.attr.from_stage, lambda x: None if not x or x == 'None' else x, enable_edit=False)
                row.notes = V.a(
                    em.long_desc,
                    href='', onclick='event.preventDefault();' + call(common.path_var_assign, str(log)),
                    cursor='pointer',
                    title=em.long_desc,
                    white_space='nowrap',
                    text_overflow='ellipsis',
                    overflow='hidden',
                    display='block',
                    width='10ch',
                )
                try:
                    name_times = g.sqlar_files(include_data=False)
                except:
                    name_times = []
                if name_times and pm.protocol == 'cell-paint':
                    dir, _, _ = name_times[0][0].partition('/')
                    show=show_protocol_dir.value == str(log)
                    row.protocol_dir = div(
                        dir,
                        pre(
                            '\n'.join([
                                f'{time} {name}'
                                for name, time, _ in name_times
                            ]),
                        ),
                        show=show,
                        css='''
                            & {
                                user-select: none;
                                cursor: pointer;
                            }
                            &[show] {
                                color: #eee;
                            }
                            & > pre {
                                display: none;
                            }
                            &[show] > pre {
                                display: block;
                                position: fixed;
                                bottom: 0;
                                left: 50%;
                                transform: translateX(-50%);
                                width: fit-content;
                                padding: 5px 9px;
                                border: 2px #000a solid;
                                color: var(--fg);
                            }
                        ''',
                        onclick=show_protocol_dir.update('' if show else str(log)),
                    )
                else:
                    row.protocol_dir= ''
                row.open = V.a('open', href='', onclick='event.preventDefault();' + call(common.path_var_assign, str(log)), class_='center')
            else:
                row.err = pre(f'{log=}: no runtime metadata')
        except BaseException as e:
            import traceback as tb
            row.err = pre(repr(e), title=tb.format_exc())
        else:
            pass
            # row.err = ''
        if 0:
            row.path = pre(
                str(log),
                onclick=call(common.path_var_assign, str(log)),
                title=
                    '\n'.join([
                        sql
                        for sql, in g.db.con.execute('select sql from sqlite_master').fetchall()
                    ] +
                    [
                        table_name + ': ' + str(g.db.con.execute(f'select * from {table_name}').fetchone())
                        for table_name, in g.db.con.execute('select name from sqlite_master').fetchall()
                    ])
            )
        if 0:
            row.mtime = pre(
                str(datetime.fromtimestamp(log.stat().st_mtime).replace(microsecond=0)),
                title=str(log),
            )
        if 'id' in row:
            del row.id
        logs += [row]
    logs = sorted(logs, key=lambda g: g.get('start_time', '1999'), reverse=False)
    yield div(
        common.make_table(logs),
        grid_area='info',
        css='''
            & {
                margin-top: 3.5em;
            }
            & input {
                border-width: 0px;
                padding: 0 7px;
                margin: 0px;
                outline: 1px grey solid;
            }
            & input:focus {
                outline-color: var(--blue);
            }
            & table td:first-child, & table th:first-child {
                min-width: unset;
            }
            & * {
                white-space: pre;
            }
            & .echo {
                padding-inline: 0px;
            }
            & input[type=checkbox] {
                outline: 0;
            }
            & .right, & .right * {
                text-align: right;
            }
            & .center {
                display: block;
                text-align: center;
            }
        '''
    )
    yield div(
        label(
            enable_edit.input().extend(transform='translateY(3px)'),
            'enable edit',
            css='''
                position: fixed;
                right: 1em;
                top: 1em;
                user-select: none;
            '''
        ),
        # label(echo.input().extend(transform='translateY(3px)'), 'enable echo'),
        grid_area='form',
        place_self='center',
        css=common.inverted_inputs_css,
    )

