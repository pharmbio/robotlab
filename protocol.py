from __future__ import annotations

from dataclasses import dataclass, field, replace, astuple
from typing import *
from datetime import datetime, timedelta

from robots import *
from utils import show

import textwrap

@dataclass(frozen=True)
class Event:
    begin: float
    end: float
    plate_id: str | None
    command: Command

def cell_painting(plate_id: str, initial_wait_seconds: float, incu_loc: str, lid_loc: str, r_loc: str, out_loc: str) -> list[Event]:
    incu_to_wash = [
        robotarm_cmd('incu_get_part1', prep=True),
        wait_for_timer_cmd(plate_id),
        incu_cmd('get', incu_loc, est=10),
        wait_for_ready_cmd('incu'),
        robotarm_cmd('incu_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    wash_to_disp = [
        robotarm_cmd('wash_get_part1', prep=True),
        wait_for_ready_cmd('wash'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd('disp_put'), # todo merge move wash -> disp
    ]

    disp_get = [
        robotarm_cmd('disp_get_part1', prep=True),
        wait_for_ready_cmd('disp'),
        robotarm_cmd('disp_get_part2'),
    ]

    disp_to_incu = [
        *disp_get,
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd('incu_put_part1'),
        incu_cmd('put', incu_loc, est=0), # should be in 37°C within a second or so
        robotarm_cmd('incu_put_part2'),
        wait_for_ready_cmd('incu'), # make sure incu is finished to be on the safe side
    ]

    disp_to_RT_incu = [
        *disp_get,
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    RT_incu_to_wash = [
        wait_for_timer_cmd(plate_id),
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'lid_{lid_loc}_put'),
        robotarm_cmd('wash_put'),
    ]

    wash_to_RT_incu = [
        robotarm_cmd('wash_get_part1', prep=True),
        wait_for_ready_cmd('wash'),
        robotarm_cmd('wash_get_part2'),
        robotarm_cmd(f'lid_{lid_loc}_get'),
        robotarm_cmd(f'{r_loc}_put'),
    ]

    to_output_hotel = [
        robotarm_cmd(f'{r_loc}_get'),
        robotarm_cmd(f'{out_loc}_put'), # postponable=True
    ]

    cmds = [
        # 2 Compound treatment
        timer_cmd(initial_wait_seconds / 60.0, plate_id),
        *incu_to_wash,
        wash_cmd('', est=90),
        *wash_to_disp,

        # 3 Mitotracker staining
        disp_cmd('peripump 1, mitotracker solution', est=15),
        *disp_to_incu,
        timer_cmd(30, plate_id),
        *incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 4 Fixation
        disp_cmd('Syringe A, 4% PFA', est=19),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 5 Permeabilization
        disp_cmd('Syringe B, 0.1% Triton X-100 in PBS', est=21),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=90),
        *wash_to_disp,

        # 6 Post-fixation staining
        disp_cmd('peripump 2, staining mixture in PBS', est=22),
        *disp_to_RT_incu,
        timer_cmd(20, plate_id),
        *RT_incu_to_wash,
        wash_cmd('pump D, PBS', est=120),

        # park it in RT, move to output hotel when there's time
        *wash_to_RT_incu,

        # 7 Imaging
        *to_output_hotel,
    ]

    t = 0.0
    events: list[Event] = []
    for cmd in cmds:
        est = cmd.time_estimate()
        t_begin = t
        t_end = t + est
        if cmd.is_prep():
            t_begin -= est
            t_end -= est
        event = Event(
            command=cmd,
            plate_id=plate_id, # (f'{plate_id}') if cmd.is_prep() else plate_id,
            begin=t_begin,
            end=t_end,
        )
        events += [event]
        t = t_end

    return events

H = [21, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]
I = [i+1 for i in range(42)]
Out = list(H)

h21 = 'h21'

incu_locs: list[str] = [f'i{i}' for i in I]
h_locs:    list[str] = [f'h{i}' for i in H]
r_locs:    list[str] = [f'r{i}' for i in H]
out_locs:  list[str] = [f'out{i}' for i in Out]
lid_locs:  list[str] = [h for h in h_locs if h != h21]

# out_locs += r_locs

from viable import *
from collections import *
import re

def make_classes(html):
    classes = {}
    def repl(m):
        decls = textwrap.dedent(m.group(1)).strip()
        if decls in classes:
            name = classes[decls]
        else:
            name = f'css-{len(classes)}'
            classes[decls] = name
        return name

    html_out = re.sub('css="([^"]*)"', repl, html, flags=re.MULTILINE)
    style = '\n'.join(
        decls.replace('&', f'[{name}]')
        if '&' in decls else
        f'[{name}] {{ {decls} }}'
        for decls, name in classes.items()
    )
    return f'''
        <style>{style}</style>
        {html_out}
    '''

from base64 import b64encode
stripe_size = 4
stripe_width = 1.2
stripes = f'''
  <svg xmlns='http://www.w3.org/2000/svg' width='{stripe_size}' height='{stripe_size}'>
    <path d='M-1,1 l2,-2
       M0,{stripe_size} l{stripe_size},-{stripe_size}
       M{stripe_size - 1},{stripe_size + 1} l2,-2' stroke='white' stroke-width='{stripe_width}'/>
  </svg>
'''
stripes = f"url('data:image/svg+xml;base64,{b64encode(stripes.encode()).decode()}')"

@serve
def index():

    zoom = int(request.args.get('zoom', '200'))
    plates = int(request.args.get('plates', '2'))
    delay = int(request.args.get('delay', '100'))
    sortby = request.args.get('sortby', 'plate')

    N = plates
    D = delay
    O = 60

    events = [
        cell_painting(f'p{i}', O + i * D, incu_loc, lid_loc, r_loc, out_loc)
        for i,                           (incu_loc, lid_loc, r_loc, out_loc) in
                      enumerate(list(zip(incu_locs, lid_locs, r_locs, out_locs))[:N])
    ]

    events = sum(events, [])
    events = sorted(events, key=lambda e: e.end)
    events = list(events)

    def execute(events: list[Event], config: Config) -> None:
        for event in events:
            event.command.execute(config) # some of the execute events are just wait until ready commands

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

    def event_machine(e):
        return event.command.__class__.__name__.rstrip('cmd').strip('_')

    with_group = []
    for index, event in enumerate(events):
        m = event_machine(event)
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

    grouped = defaultdict(list)
    for g, e in sorted(with_group, key=lambda xy: xy[0]):
        grouped[g] += [e]

    tbl = []
    for g, events in grouped.items():
        divs = ''
        for event in events:
            machine = event_machine(event)
            color = dict(
                wait_for_ready='color0',
                wait_for_timer='color0',
                robotarm='color4',
                wash='color6',
                disp='color1',
                incu='color2',
                timer='color3',
            )
            color_var = f'--{color.get(machine, "color15")}'
            try:
                prep = event.command.prep
            except:
                prep = False
            divs = f'''
                <div {'css-stripes' if prep else ''}
                    style="
                        --begin:  calc(var(--zoom) * {event.begin}px);
                        --end:    calc(var(--zoom) * {event.end}px);
                        --color:  var({color_var});
                    "
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
                    data-info="
                        {esc(str(event))}
                    "
                    onmouseover="
                        document.querySelector('#info').innerHTML = this.dataset.info.trim()
                    "
                    onmouseout="
                        document.querySelector('#info').innerHTML = ''
                    "
                ></div>
            ''' + divs

        tbl += [f'''
            <tr>
                <td>{event.plate_id}</td>
                <td>{esc(machine)}</td>
                <td css="
                        width: 100000px;
                        position: relative;
                    ">{divs}</td>
            </tr>
        ''']

    nl = '\n'
    return '''
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
                background: #f2f2f2;
            }
            tr:hover {
                background: #cef;
            }
            table, tr {
                width: 10000px;
            }
            td {
                padding: 0 5px;
            }
            [css-stripes] {
                background-image: ''' + stripes + ''';
            }
        </style>
    ''' + make_classes(f'''
        <form
            onchange="console.log(event, this); set_query(this); refresh(); return false"
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
               <input type="range" id="zoom" name="zoom" min="1" max="400" value={zoom} style="width:600px">zoom: {zoom}
           </div>
           <div>
               <input type="range" id="plates" name="plates" min="1" max="10" value={plates} style="width:600px">plates: {plates}
           </div>
           <div>
               <input type="range" id="delay" name="delay" min="0" max="500" value={delay} style="width:600px">delay: {delay}
           </div>
           <div>
               sort by:
               <label><input type="radio" name="sortby" id="machine,plate" value="machine,plate" {"checked" if sortby == "machine,plate" else ""}>machine,plate</label>
               <label><input type="radio" name="sortby" id="plate,machine" value="plate,machine" {"checked" if sortby == "plate,machine" else ""}>plate,machine</label>
               <label><input type="radio" name="sortby" id="plate" value="plate" {"checked" if sortby == "plate" else ""}>plate</label>
               <label><input type="radio" name="sortby" id="machine" value="machine" {"checked" if sortby == "machine" else ""}>machine</label>
           </div>
        </form>
        <div css="height: 120px"></div>
        <table style="--zoom: {zoom / 100.0}; margin-top: 20px;">
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
    ''')

