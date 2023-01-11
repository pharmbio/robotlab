from __future__ import annotations
from typing import *
from dataclasses import *

from viable import store, js, call, Serve, Flask, Int, Str, Bool
from viable import Tag, div, span, label, button, pre
import viable as V

from pathlib import Path
from subprocess import Popen, DEVNULL
import json
import platform
import shlex
import textwrap
import subprocess

from ..cli import Args
from .. import cli

import pbutils
from ..small_protocols import small_protocols_dict, SmallProtocolData
from ..runtime import RuntimeConfig

from . import common

from urllib.parse import quote_plus

def start(args: Args, simulate: bool, config: RuntimeConfig, push_state: bool=True):
    config_name = 'simulate' if simulate else config.name
    log_filename = cli.args_to_filename(replace(args, config_name=config_name))
    args = replace(
        args,
        config_name=config_name,
        log_filename=log_filename,
        force_update_protocol_dir='live' in config.name,
        yes=True,
    )
    Path('cache').mkdir(exist_ok=True)
    cmd = [
        'sh', '-c',
        '''
            echo starting... >"$2"
            cellpainter --json-arg "$1" 2>>"$2"
        ''',
        '--',
        json.dumps(pbutils.nub(args)),
        common.as_stderr(log_filename),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    common.path_var_assign(log_filename, push_state=push_state)

form_css = '''
    & {
        display: grid;
        grid-template-columns: auto auto;
        place-items: center;
        grid-gap: 10px;
        margin: 0 auto;
        user-select: none;
    }
    & input {
        border: 1px #0003 solid;
        border-right-color: #fff2;
        border-bottom-color: #fff2;
    }
    & button {
        border-width: 1px;
    }
    & input, & button, & select {
        padding: 8px;
        border-radius: 2px;
        background: var(--bg);
        color: var(--fg);
    }
    & select.two {
        padding: 0;
    }
    & select.two option {
        padding-left: 8px;
    }
    & select {
        width: 100%;
        padding-left: 4px;
    }
    & input:focus-visible, & button:focus-visible, & select:focus-visible {
        outline: 2px  var(--blue) solid;
        outline-color: var(--blue);
    }
    & input:hover {
        border-color: var(--blue);
    }
    & .wide {
        grid-column: 1 / span 2;
    }
    & > button {
        width: 100%;
    }
    & > label {
        display: contents;
        cursor: pointer;
    }
    & > label > span {
        justify-self: right;
    }
    & input, & select {
        width: 300px;
    }
    & > label > span {
        grid-column: 1;
    }
''' + common.inverted_inputs_css

def start_form(*, config: RuntimeConfig):
    options = {
        'cell-paint': 'cell-paint',
        **{
            k.replace('_', '-'): v
            for k, v in small_protocols_dict.items()
        }
    }

    protocol = store.str(default='cell-paint', options=tuple(options.keys()))
    store.assign_names(locals())

    desc = store.str(name='description', desc='Example: "specs395-v1"')
    operators = store.str(name='operators', desc='Example: "Amelie and Christa"')
    incu = store.str(name='incubation times', default='20:00', desc='The incubation times in seconds or minutes:seconds, separated by comma. If too few values are specified, the last value is repeated. Example: 21:00,20:00')
    batch_sizes = store.str(default='6', name='batch sizes', desc='The number of plates per batch, separated by comma. Example: 6,6')
    protocol_dir = store.str(default='automation_v5.0', name='protocol dir', desc='Directory on the windows computer to read biotek LHC files from')
    final_washes = store.str(name='final wash rounds', options=['one', 'two'], desc='Number of final wash rounds. Either run 9_W_*.LHC once or run 9_10_W_*.LHC twice.')

    num_plates = store.str(name='plates', desc='The number of plates')
    params = store.str(name='params', desc=f'Additional parameters to protocol "{protocol.value}"')
    store.assign_names(locals())

    small_data = options.get(protocol.value)

    form_fields: list[Str | Bool] = []
    if protocol.value == 'cell-paint':
        form_fields = [
            desc,
            operators,
            batch_sizes,
            incu,
            protocol_dir,
            final_washes,
        ]
        bs = batch_sizes.value
        incu_csv = incu.value
        args = Args(
            cell_paint=bs,
            incu=incu_csv,
            interleave=True,
            two_final_washes=final_washes.value == 'two',
            lockstep_threshold=10,
            protocol_dir=protocol_dir.value,
            desc=desc.value,
            operators=operators.value,
        )
    elif isinstance(small_data, SmallProtocolData):
        if 'num_plates' in small_data.args:
            form_fields += [num_plates]
        if 'params' in small_data.args:
            form_fields += [params]
        if 'protocol_dir' in small_data.args:
            form_fields += [protocol_dir]
        args = Args(
            small_protocol=small_data.name,
            num_plates=pbutils.catch(lambda: int(num_plates.value), 0),
            params=pbutils.catch(lambda: shlex.split(params.value), []),
            protocol_dir=protocol_dir.value,
        )
    else:
        form_fields = []
        args = None

    if args:
        try:
            stages = cli.args_to_stages(replace(args, incu='x'))
        except:
            stages = []
        if stages:
            start_from_stage = store.str(
                name='start from stage',
                default='start',
                desc='Stage to start from',
                options=stages
            )
            form_fields += [start_from_stage]
            if start_from_stage.value:
                args = replace(args, start_from_stage=start_from_stage.value)

    if isinstance(small_data, SmallProtocolData):
        doc_full = textwrap.dedent(small_data.make.__doc__ or '').strip()
        doc_header = small_data.doc
        doc_divs = [
            div(
                # fill
                grid_column='1 / span 2',
                grid_row='2 / span 2',
            ),
            div(
                doc_header,
                title=doc_full,
                grid_column='2 / span 1',
                grid_row='2 / span 2',
                css='''
                    max-width: fit-content;
                    padding: 5px 12px;
                    place-self: start;
                ''',
            ),
        ]
    else:
        doc_full = ''
        doc_divs = []

    confirm = ''
    if 'required' in doc_full.lower():
        confirm = doc_full
    if not confirm and args and args.cell_paint:
        if not args.desc:
            confirm += 'Not specified: description.\n'
        if not args.operators:
            confirm += 'Not specified: operators.\n'
        if confirm:
            confirm += '\nStart anyway?'
    yield div(
        *common.form(protocol),
        *doc_divs,
        *common.form(*form_fields),
        button(
            'simulate',
            onclick=call(start, args=args, simulate=True, config=config),
            grid_row='-1',
        ) if args else '',
        button(
            common.triangle(), ' ', 'start',
            data_doc=doc_full,
            data_confirm=confirm,
            onclick=
                (
                    'confirm(this.dataset.confirm) && '
                    if confirm
                    else ''
                )
                +
                call(start, args=args, simulate=False, config=config),
            grid_row='-1',
        ) if args else '',
        height='100%',
        padding='80px 0',
        grid_area='form',
        user_select='none',
        css_=form_css,
        css='''
            & {
                grid-template-rows: repeat(8, 40px);
                grid-template-columns: 160px 300px;
            }
            & label > span {
                text-align: right;
            }
            & button {
                height: 100%;
            }
        '''
    )
    running_processes: list[tuple[int, str]] = []
    try:
        x = subprocess.check_output(['pgrep', '^cellpainter$']).decode()
    except:
        x = ''
    for pid in x.strip().split('\n'):
        try:
            pid = int(pid)
            process_args = common.get_json_arg_from_argv(pid)
            if isinstance(v := process_args.get("log_filename"), str):
                pbutils.pr(args)
                running_processes += [(pid, v)]
        except:
            pass

    info = div(
        grid_area='info',
        z_index='1',
        css='''
            & li {
                margin: 8px 0;
            }
            & > div {
                margin: 16px 0;
            }
        '''
    )
    if running_processes:
        ul = V.ul()
        for pid, arg in running_processes:
            ul += V.li(
                V.span(
                    arg,
                    onclick=call(common.path_var_assign, arg),
                    text_decoration='underline',
                    cursor='pointer'
                ),
                V.button(
                    'kill',
                    data_arg=arg,
                    onclick=
                        'window.confirm("Really kill " + this.dataset.arg + "?") && ' +
                        call(common.sigkill, pid),
                    py=5, mx=8, my=0,
                    border_radius=3,
                    border_width=1,
                    border_color='var(--red)',
                ),
            )
        info += div('Running processes:', ul)
    vis = '/vis'
    if args:
        vis = '/vis?cmdline=' + quote_plus(cli.args_to_str(args))
    info += div(
        'More:',
        V.ul(
            # V.li(V.a('show timings', href='/timings')),
            V.li(V.a('show logs', href='/logs')),
            V.li(V.a('show in visualizer', href=vis)),
        ),
    )
    yield info
    yield div(
        f'Running on {platform.node()} with config {config.name}',
        grid_area='info-foot',
        opacity='0.85',
        margin='0 auto',
    )
