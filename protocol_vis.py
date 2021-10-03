from __future__ import annotations
from typing import *

from viable import head, serve, esc, css_esc, trim, button, pre
from viable import Tag, div, span, label, img, raw, Input, input
import viable as V

from flask import request
from collections import *
import re
import textwrap

import utils

from protocol import Event
import protocol
from robots import RuntimeConfig, configs

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
    store: dict[str, str | bool] = {}
    zoom_input = Input(store, 'zoom', 'text', default='1')
    batch_size_input = Input(store, 'batch_size', 'text', default='6')

    zoom = utils.catch(lambda: float(store['zoom']), 1)
    batch_size = utils.catch(lambda: int(store['batch_size']), 6)

    with utils.timeit('eventlist'):
        events = protocol.eventlist(batch_sizes=[batch_size], protocol_config=protocol.v3)
    with utils.timeit('runtime'):
        runtime = protocol.execute_events(configs['dry-run-no-log'], events, {})

    entries = runtime.log_entries

    with utils.timeit('area'):
        area = div(style=f'''
            width: 100%;
            height: {zoom * max(e.get('t', 0) for e in entries)}px;
        ''', css='''
            position: relative;
        ''')
        for e in entries:
            t0 = e.get('t0')
            t = e.get('t')
            if t0 is None or t is None:
                continue
            if 'idle' in str(e.get('source')):
                continue
            # if 'wait' in str(e.get('source')):
                # continue
            # part    = e.get('event_part', '')
            # subpart = e.get('event_subpart', '')
            # plate   = e.get('event_plate_id', '')
            slots = {
                'incu': 1,
                'wait': 2,
                'robotarm': 3,
                'wash': 4,
                'disp': 5,
                'checkpoint': 6,
            }
            color_map = {
                'wait': 'color3',
                'idle': 'color3',
                'robotarm': 'color4',
                'wash': 'color6',
                'disp': 'color5',
                'incu': 'color2',
                'timer': 'color3',
            }
            slot = slots.get(e.get('source', ''), 0)
            slot += (1 + max(slots.values())) * utils.catch(lambda: int(e['event_plate_id']), 0)
            # slot += batch_size * slot + utils.catch(lambda: int(e['event_plate_id']), 0)
            # slot = utils.catch(lambda: int(e['event_plate_id']), 0)
            color = colors.get(color_map.get(e.get('source', ''), ''), '#ccc')
            width = 14
            my_width = 14
            if e.get('source') == 'checkpoint':
                my_width = 7
                # continue
            area += div(
                css='''
                    position: absolute;
                    border-radius: 2px;
                    border: 1px #0005 solid;
                ''',
                style=trim(f'''
                    left: {slot * width:.1f}px;
                    width: {my_width - 2:.1f}px;
                    top: {zoom * t0:.1f}px;
                    height: {zoom * (t - t0):.1f}px;
                    background: {color};
                '''),
                data_info=utils.show(e, use_color=False)
            )

    area.onmouseover += """
        if (event.target.dataset.info)
            document.querySelector('#info').innerHTML = event.target.dataset.info.trim()
    """

    area.onmouseout += """
        if (event.target.dataset.info)
            document.querySelector('#info').innerHTML = ''
    """

    yield {
        'sheet': '''
            body, html {
                font-family: monospace;
                font-size: 12px;
            }
        '''
    }
    # yield zoom_input
    # yield batch_size_input
    yield area

    yield div(' ', style="height:400px")

    yield pre(
        id="info",
        css='''
            position: fixed;
            right: 0;
            bottom: 0;
            margin: 0;
            padding: 10px;
            background: #fff;
            z-index: 1;
            position: fixed;
            border-radius: 5px;
            border: 1px #0005 solid;
        ''')

