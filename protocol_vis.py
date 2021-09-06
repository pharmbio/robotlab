from __future__ import annotations
from typing import *

from viable import head, serve, esc, make_classes
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

def now():
    import datetime
    t = datetime.datetime.now()
    s = t.strftime('%Y-%m-%d %H:%M:%S.%f')
    return s[:-3]

@serve
def index() -> Iterator[head | str]:
    zoom = int(request.args.get('zoom', '200'))
    num_batches = int(request.args.get('num_batches', '1'))
    batch_size = int(request.args.get('batch_size', '2'))
    between_batch_delay_str: str = request.args.get('between_batch_delay', 'auto')
    within_batch_delay_str: str = request.args.get('within_batch_delay', 'auto')
    events, between_batch_delay, within_batch_delay = protocol.cell_paint_batches_parse_delay(
        num_batches,
        batch_size,
        between_batch_delay_str,
        within_batch_delay_str,
    )
    sortby: str = request.args.get('sortby', 'plate')

    print(f'{between_batch_delay=}')
    print(f'{within_batch_delay=}')
    events = protocol.sleek_movements(events)

    with_group: list[tuple[tuple[int | str | None, ...], Event]] = []
    for index, event in enumerate(events):
        m = event.machine()
        if 'wait' in m:
            continue
        i = dict(
            timer=0,
            incu=1,
            wash=2,
            robotarm=3,
            disp=4,
        ).get(m, 99)
        sortable = dict(
            machine=i,
            plate=event.plate_id
        )
        with_group += [
            (tuple(sortable.get(s) for s in sortby.split(',')),
             event)
        ]

    grouped: defaultdict[tuple[int | str | None, ...], list[Event]] = defaultdict(list)
    for g, e in sorted(with_group, key=lambda xy: xy[0]):
        grouped[g] += [e]

    tbl: list[str] = []
    for g, events in grouped.items():
        divs = ''
        overlaps = False
        for event in events:
            machine = event.machine()
            color = dict(
                wait_for_ready='color0',
                wait_for_timer='color0',
                robotarm='color4',
                wash='color6',
                disp='color5',
                incu='color2',
                timer='color3',
            )
            color_var = f'--{color.get(machine, "color15")}'
            try:
                prep = event.command.prep # type: ignore
            except:
                prep = False
            overlap = event.overlap.value
            overlaps |= overlap
            divs = f'''
                <div {'css-stripes' if prep else ''} {'css-overlap' if overlap else ''}
                    css="
                        background-color: var(--color);
                        --width: calc(var(--end) - var(--begin));
                        position: absolute;
                        left: var(--begin);
                        width: var(--width);
                        top: 0;
                        height: 100%;
                        border-radius: 4px;
                        box-shadow:
                            inset  1px  0px #0006,
                            inset  0px  1px #0006,
                            inset -1px  0px #0006,
                            inset  0px -1px #0006;
                    "
                    style="
                        --begin:  calc(var(--zoom) / 100 * {event.begin}px);
                        --end:    calc(var(--zoom) / 100 * {event.end}px);
                        --color:  var({color_var});
                    "
                    data-info="{esc(utils.show(event, use_color=False))}"
                ></div>
            ''' + divs

        tbl += [f'''
            <tr>
                <td>{event.plate_id}</td>
                <td>{esc(machine)}</td>
                <td {'css-overlap-outline' if overlaps else ''}
                        onmouseover="
                            if (event.target.dataset.info)
                                document.querySelector('#info').innerHTML = event.target.dataset.info.trim()
                        "
                        onmouseout="
                            if (event.target.dataset.info)
                                document.querySelector('#info').innerHTML = ''
                        "
                    css="

                        width: 100000px;
                        position: relative;
                    ">{textwrap.dedent(divs)}</td>
            </tr>
        ''']

    nl = '\n'
    yield head('''
        <style>
            body, html {
                font-family: monospace;
                font-size: 22px;
                ''' + colors_css + '''
                background: var(--background);
                color: var(--foreground);
                position: relative;
            }
            label {
                cursor: pointer;
            }
            tr:nth-child(even) {
                background-color: #f2f2f2;
            }
            tr:hover {
                background-color: #cef;
            }
            table, tr {
                width: 10000px;
            }
            td {
                padding: 0 5px;
            }
            [css-stripes] {
                background-image: ''' + stripes_up + ''';
            }
            [css-overlap] {
                background-image: ''' + stripes_dn + ''';
            }
            [css-overlap-outline] {
                background-image: ''' + stripes_dn_faint + ''';
            }
        </style>
    ''')
    yield f'''
        <body style="--zoom: {zoom};">
        <form
            nonchange="set_query(this); refresh()"
            oninput="set_query(this); refresh()"
            css="
                position: fixed;
                left: 0;
                top: 0;
                padding: 10px;
                background: #fff;
                z-index: 1;
                width: 100vw;
            "
            css="
               & input {{
                   margin-right: 10px;
               }}
            "
        >

           <div>
               <input type="range" id="zoom" name="zoom" min="1" max="400" value={zoom} style="width:600px"
                onchange="
                    event.stopPropagation();
                    set_query(this.closest('form'))
                    document.body.style='--zoom: ' + this.value;
                "
                oninput="
                    event.stopPropagation();
                    set_query(this.closest('form'))
                    document.body.style='--zoom: ' + this.value;
                "
               >zoom: <span css="&::after {{
                            counter-reset: zoom var(--zoom);
                            content: counter(zoom);
                            }}" />

           </div>
           <div><input type="range" id="num_batches" name="num_batches" min="1" max="10" value={num_batches} style="width:600px">num_batches: {num_batches}</div>
           <div><input type="range" id="batch_size" name="batch_size" min="1" max="10" value={batch_size} style="width:600px">batch_size: {batch_size}</div>
           <div><input type="range" id="between_batch_delay" name="between_batch_delay" min="3600" max="10800" value={between_batch_delay} style="width:600px">between_batch_delay: {between_batch_delay}</div>
           <div><input type="range" id="within_batch_delay" name="within_batch_delay" min="0" max="500" value={within_batch_delay} style="width:600px">within_batch_delay: {within_batch_delay}</div>
           <div>
               sort by:
               <label><input type="radio" name="sortby" id="machine,plate" value="machine,plate" {"checked" if sortby == "machine,plate" else ""}>machine,plate</label>
               <label><input type="radio" name="sortby" id="plate,machine" value="plate,machine" {"checked" if sortby == "plate,machine" else ""}>plate,machine</label>
               <label><input type="radio" name="sortby" id="plate"         value="plate"         {"checked" if sortby == "plate"         else ""}>plate</label>
               <label><input type="radio" name="sortby" id="machine"       value="machine"       {"checked" if sortby == "machine"       else ""}>machine</label>
           </div>
        </form>
        <div css="height: 160px"></div>
        <table css="margin-top: 20px;">
           {nl.join(tbl)}
        </table>
        <div css="height: 50px"></div>
        <pre id="info"
            css="
                position: fixed;
                left: 0;
                bottom: 0;
                margin: 0;
                padding: 10px;
                background: #fff;
                z-index: 1;
                position: fixed;
            "
            ></pre>
    '''

