from __future__ import annotations
from typing import *

from viable import *
from collections import *
import re

from protocol import *

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
    return head(f'<style>{style}</style>'), html_out

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

from base64 import b64encode
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
def b64svg(s):
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
def index():

    zoom = int(request.args.get('zoom', '200'))
    plates = int(request.args.get('plates', '2'))
    delay_str = request.args.get('delay', 'auto')
    if delay_str == 'auto':
        delay: Literal['auto'] = 'auto'
    else:
        delay = int(delay_str)
    sortby = request.args.get('sortby', 'plate')

    events = cell_paint_many(plates, delay, offset=60)

    def execute(events: list[Event], config: Config) -> None:
        for event in events:
            event.command.execute(config) # some of the execute events are just wait until ready commands

    with_group = []
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

    grouped = defaultdict(list)
    for g, e in sorted(with_group, key=lambda xy: xy[0]):
        grouped[g] += [e]

    tbl = []
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
                prep = event.command.prep
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
                    data-info="{esc(str(event))}"
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
                    ">{dedent(divs)}</td>
            </tr>
        ''']

    nl = '\n'
    return head('''
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
    '''), make_classes(f'''
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
               <label><input type="radio" name="sortby" id="plate"         value="plate"         {"checked" if sortby == "plate"         else ""}>plate</label>
               <label><input type="radio" name="sortby" id="machine"       value="machine"       {"checked" if sortby == "machine"       else ""}>machine</label>
           </div>
        </form>
        <div css="height: 120px"></div>
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
    ''')

