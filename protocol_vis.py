from __future__ import annotations
from typing import *

from viable import app
from viable import head, serve, esc, css_esc, trim, button, pre
from viable import Tag, div, span, label, img, raw, Input, input
import viable as V

from flask import request
from collections import *

import utils

import protocol
from runtime import RuntimeConfig, dry_run

colors = dict(
    background = '#fff',
    color0 =     '#2d2d2d',
    color1 =     '#f2777a',
    color2 =     '#99cc99',
    color3 =     '#ffcc66',
    color4 =     '#6699cc',
    color5 =     '#cc99cc',
    color6 =     '#66cccc',
    color7 =     '#d3d0c8',
    color8 =     '#747369',
    color9 =     '#f99157',
    color10 =    '#393939',
    color11 =    '#515151',
    color12 =    '#a09f93',
    color13 =    '#e8e6df',
    color14 =    '#d27b53',
    color15 =    '#f2f0ec',
    foreground = '#333',
)

colors_css = '\n    '.join(f'--{k}: {v};' for k, v in colors.items())

stripe_size = 4
stripe_width = 1.2
sz = stripe_size
stripes_up = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{sz}' height='{sz}'>
    <path d='
       M{-sz},{1*sz} l{3*sz},{-3*sz}
       M{-sz},{2*sz} l{3*sz},{-3*sz}
       M{-sz},{3*sz} l{3*sz},{-3*sz}
    ' stroke='white' stroke-width='{stripe_width}'/>
  </svg>
'''
stripes_dn = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{sz}' height='{sz}'>
    <path d='
       M{-sz},{-0*sz} l{3*sz},{3*sz}
       M{-sz},{-1*sz} l{3*sz},{3*sz}
       M{-sz},{-2*sz} l{3*sz},{3*sz}
    ' stroke='{colors["color1"]}' stroke-width='{stripe_width}'/>
  </svg>
'''
stripes_dn_faint = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{sz}' height='{sz}'>
    <path d='
       M{-sz},{-0*sz} l{3*sz},{3*sz}
       M{-sz},{-1*sz} l{3*sz},{3*sz}
       M{-sz},{-2*sz} l{3*sz},{3*sz}
    ' stroke='{colors["color1"]}88' stroke-width='{stripe_width}'/>
  </svg>
'''

from base64 import b64encode
def b64svg(s: str):
    return f"url('data:image/svg+xml;base64,{b64encode(s.encode()).decode()}')"

stripes_html = stripes_up
stripes_up = b64svg(stripes_up)
stripes_dn = b64svg(stripes_dn)
stripes_dn_faint = b64svg(stripes_dn_faint)

coords = ''
n = 0

@serve.one('/')
def index() -> Iterator[Tag | dict[str, str]]:

    yield {
        'sheet': '''
            body, html {
                font-family: monospace;
                font-size: 12px;
            }
        '''
    }
    yield {
        'onkeydown': '''
            if (event.key == 'Enter') {
                update_query(input_values())
                refresh()
            }
        ''',
        'oninput': '''
            if (event.target?.type != 'text') {
                update_query(input_values())
                refresh()
            }
        ''',
        'sheet': '''
            label {
                display: grid;
                padding: 2px;
                width: 400px;
                grid-template-columns: 1fr 1fr;
                align-items: center;
                grid-gap: 4px;
            }
            label > :nth-child(1) {
                justify-self: right;
            }
        '''
    }
    store: dict[str, str | bool] = {}
    yield label(span('zoom: '),       Input(store, 'zoom', type='text', default='1'))
    yield label(span('batch sizes:'), Input(store, 'batch_size', type='text', default='6'))
    yield label(span('incubation times:'), Input(store, 'incu', type='text', default='1200'))
    yield label(Input(store, 'interleave', type='checkbox', default=False), div('interleave'))
    yield label(Input(store, 'lockstep', type='checkbox', default=False),   div('lockstep'))
    yield label(Input(store, 'six', type='checkbox', default=False),        div('two final washes'))

    zoom       = utils.catch(lambda: float(store['zoom']), 1)
    batch_size = utils.catch(lambda: int(store['batch_size']), 6)

    # v3 = protocol.make_v3(incu_csv='t1, t2, t3, t4, t5', interleave=True, six=True, lockstep=True)
    # v3 = protocol.make_v3(incu_csv='22:15, 22:05, 22:05, 22:15, t5', interleave=True, six=True, lockstep=True)
    v3 = protocol.make_v3(
        incu_csv   = str(store.get('incu', '1200')),
        interleave = bool(store.get('interleave')),
        six        = bool(store.get('six')),
        lockstep   = bool(store.get('lockstep')),
    )

    try:
        with utils.timeit('eventlist'):
            program = protocol.cell_paint_program(batch_sizes=[batch_size], protocol_config=v3)
        with utils.timeit('runtime'):
            config = dry_run.replace(log_to_file=False)
            runtime = protocol.execute_program(config, program, {})
    except:
        import traceback
        yield pre(traceback.format_exc())
        return

    import timings
    utils.pr(timings.Guesses)

    entries = runtime.log_entries

    txt: list[str] = []

    for k, vs in protocol.group_times(runtime.times).items():
        if '37C' in k:
            txt += [' '.join((k, *vs))]
        if 'active' in k:
            txt += [' '.join((k, *vs))]
        if 'incubation' in k:
            txt += [' '.join((k, *vs))]
        if 'transfer' in k:
            txt += [' '.join((k, *vs))]
        if 'lid' in k:
            txt += [' '.join((k, *vs))]
        if 'batch' in k:
            txt += [' '.join((k, *vs))]

    yield pre('\n'.join(txt))

    with utils.timeit('area'):
        area = div(style=f'''
            width: 100%;
            height: {zoom * max(e.get('t', 0) for e in entries)}px;
        ''', css='''
            position: relative;
        ''')
        for e in entries:
            try:
                slot     = e.get('slot')
                plate    = utils.catch(lambda: int(e.get('plate_id', 0)), 0)
                t0       = e['t0']
                t        = e['t']
                source   = e['source']
                resource = e.get('resource')
                arg      = e['arg']
            except:
                continue
            if t0 is None:
                continue
            color_map = {
                'wait': 'color3',
                'idle': 'color3',
                'robotarm': 'color4',
                'wash': 'color6',
                'disp': 'color5',
                'incu': 'color2',
                'timer': 'color3',
            }
            if slot is None:
                slot = {
                    'incu': 1,
                    'wash': 2,
                    'disp': 3,
                }.get(resource or '', 1)
            slot = 2 * slot - 2
            if resource in ('wash', 'disp', 'incu'):
                slot += 1
            if source == 'duration':
                slot = 10 + plate
            color = colors.get(color_map.get(source, ''), '#ccc')
            width = 14
            my_width = 14
            my_offset = 0
            z_index = 0
            if source == 'duration':
                my_width = 4
                z_index = 1
                if 'transfer' in arg:
                    color = colors.get('color1')
                    z_index = 2
                if 'lid' in arg:
                    my_offset += 4
                if 'pre disp' in arg:
                    my_offset += 8
                if '37C' in arg:
                    my_offset += 4
                    color = colors.get(color_map['incu'])
            if source == 'wait':
                my_width = 7
                z_index = 1
            if source == 'idle':
                my_width = 7
                z_index = 2
            if source == 'run':
                continue
            area += div(
                str(plate) if t - t0 > 9.0 and my_width > 4 and plate else '',
                css='''
                    position: absolute;
                    border-radius: 2px;
                    border: 1px #0005 solid;
                    display: grid;
                    place-items: center;
                    font-size: 0.8em;
                ''',
                style=trim(f'''
                    left: {slot * width + my_offset:.1f}px;
                    width: {my_width - 2:.1f}px;
                    top: {zoom * t0:.1f}px;
                    height: {zoom * (t - t0) - 1:.1f}px;
                    background: {color};
                    z-index: {z_index};
                '''),
                data_info=utils.show({
                    k: utils.pp_secs(v) if k in 't t0 duration'.split() else v
                    for k, v in e.items()
                }, use_color=False)
            )

    area.onmouseover += """
        if (event.target.dataset.info)
            document.querySelector('#info').innerHTML = event.target.dataset.info.trim()
    """

    area.onmouseout += """
        if (event.target.dataset.info)
            document.querySelector('#info').innerHTML = ''
    """
    # yield zoom_input
    # yield batch_size_input
    yield area

    yield div(' ', style="height:400px")

    yield pre(
        id="info",
        css='''
            position: fixed;
            left: 0;
            bottom: 0;
            margin: 0;
            padding: 10px;
            background: #fff;
            z-index: 10;
            position: fixed;
            border-radius: 5px;
            border: 1px #0005 solid;
        ''')

