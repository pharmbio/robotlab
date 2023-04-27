from __future__ import annotations
from typing import *

from viable import Serve, js, store, Flask, call
from viable import Tag, pre, div, span, label

from .log import Log
from . import commands

import pbutils

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

from functools import lru_cache

def start(cmdline0: str, cmdline_to_log: Callable[[str], Log]):
    # cmdline_to_log = lru_cache(cmdline_to_log)
    serve = Serve(_app := Flask(__name__))
    add_to_serve(serve, cmdline0, cmdline_to_log)
    serve.run()

def add_to_serve(serve: Serve, cmdline0: str, cmdline_to_log: Callable[[str], Log], route: str='/'):

    cmdline_to_log = lru_cache(cmdline_to_log)

    @serve.route(route)
    def index() -> Iterator[Tag | dict[str, str]]:

        yield {
            'sheet': '''
                *, *::before, *::after {
                    box-sizing: border-box;
                    margin: 0;
                }
                html, body {
                    height: auto;
                    min-height: 100%;
                }
                body, html {
                    font-family: monospace;
                }
                body > * {
                    padding: 16px;
                }
                html {
                    --bg:        #2d2d2d;
                    --bg-bright: #383838;
                    --bg-brown:  #554535;
                    --fg:        #d3d0c8;
                    --red:       #f2777a;
                    --brown:     #d27b53;
                    --green:     #99cc99;
                    --yellow:    #ffcc66;
                    --blue:      #6699cc;
                    --purple:    #cc99cc;
                    --cyan:      #66cccc;
                    --orange:    #f99157;
                }
            '''
        }
        yield {
            'sheet': '''
                label {
                    display: grid;
                    padding: 2px;
                    grid-template-columns: 150px 1fr 150px ;
                    align-items: center;
                    grid-gap: 4px;
                }
                label > :nth-child(1) {
                    justify-self: right;
                }
            '''
        }
        cmdline = store.query.str(cmdline0)
        delay_ids = store.query.str('')
        delay_secs = store.query.int(0, min=0, max=60)
        zoom_int = store.query.int(100, min=1, max=1000)
        vertical = store.query.bool(True)
        pfa_duration = store.query.int(15, min=0, max=100)
        store.assign_names(locals())
        zoom = zoom_int.value / 100.0
        yield div(
            div(
                label(span('cmdline: '), cmdline.input(iff='0').extend(
                    onkeydown='event.key == "Enter" && ' + cmdline.update(js('this.value'))
                )),
                label(span('sim delay: '),
                    div(
                        delay_ids.input(),
                        delay_secs.range(),
                        style='''
                            display: grid;
                            grid-template-columns: 100px 1fr;
                            grid-gap: 10px;
                        '''
                    ),
                    span(f'{delay_secs.value} s'),
                ),
                label(span('zoom: '), zoom_int.range(), span(str(zoom_int.value))),
                label(span('pfa duration: '), pfa_duration.range().extend(width=200), span(f'{pfa_duration.value} s')),
                label(span('vertical: '), vertical.input().extend(style='justify-self: left')),
                background='#fff',
                border_bottom='1px #0008 solid',
                p=20,
                m=0,
            ),
            position='fixed',
            top=0,
            p=0,
            width='100%',
            z_index='1' + '0' * 9,
        )

        yield div(mb=170, p=0)

        try:
            if delay_ids.value and delay_secs.value:
                sim_delay = f' --sim-delay {delay_ids.value}:{delay_secs.value}'
            else:
                sim_delay = ''
            if 'example' in cmdline.value:
                line = cmdline.value + sim_delay + f' {pfa_duration.value}'
            else:
                line = cmdline.value + sim_delay
            log = cmdline_to_log(line)
            entries = log.command_states().list()
        except:
            import traceback
            traceback.print_exc()
            yield pre(traceback.format_exc())
            return

        if 1 or vertical.value:
            from . import estimates
            if estimates.guesses:
                pbutils.pr(estimates.guesses)

            yield pre('\n'.join(log.group_durations_for_display()))

        area = div(style=f'''
            width: 100%;
            -height: {zoom * max(e.t for e in entries)}px;
        ''', css='''
            & {
                position: relative;
                user-select: none;
                -transform: translateY(-50%) rotate(90deg) scaleX(-1);
            }
            & > * > span {
                -transform: translate(-25%, -25%) rotate(90deg) scaleX(-1);
            }
        ''')
        for e in reversed(entries):
            t0 = e.t0
            t = e.t
            cmd = e.cmd
            m = e.metadata
            slot = m.slot
            plate = pbutils.catch(lambda: int(m.plate_id or '0'), 0)
            machine = e.machine() or ''
            sources: dict[Any, str] = {
                commands.Idle: 'idle',
                commands.WaitForCheckpoint: 'wait',
                commands.Duration: 'duration',
            }
            source = sources.get(e.cmd.__class__, machine) or ''
            if t0 is None:
                continue
            if slot == 0:
                slot = {
                    'fridge': 2,
                    'incu': 2,
                    'wash': 3,
                    'blue': 3,
                    'disp': 4,
                    'nikon': 3,
                    'squid': 3,
                    None: 1
                }.get(m.thread_resource, 1)
            slot = 2 * slot
            if machine in ('', 'robotarm', 'pf'):
                slot -= 1
            if isinstance(e.cmd, commands.WaitForCheckpoint):
                slot -= 1
            if isinstance(e.cmd, commands.Checkpoint):
                continue
            if source == 'duration':
                slot = 10 + plate
            slot += 1
            color_map = {
                '':         'var(--fg)',
                'wait':     'var(--yellow)',
                'idle':     'var(--yellow)',
                'robotarm': 'var(--blue)',
                'pf':       'var(--blue)',
                'wash':     'var(--cyan)',
                'blue':     'var(--cyan)',
                'disp':     'var(--purple)',
                'incu':     'var(--green)',
                'fridge':   'var(--cyan)',
                'squid':    'var(--red)',
                'nikon':    'var(--orange)',
            }
            color = color_map.get(source, '#ccc')
            fg_color = '#000'
            width = 14
            my_width = 14
            my_offset = 0
            if not vertical.value:
                slot = {
                    'incu': 3,
                    'fridge': 2,
                    'wash': 2,
                    'blue': 2,
                    'disp': 1,
                    'nikon': 3,
                    'squid': 3,
                    None: 0,
                }.get(m.thread_resource, 0)
                if isinstance(cmd, commands.Duration):
                    continue
                    slot = 4
            if isinstance(cmd, commands.Duration):
                my_width = 4
                if 'transfer' in cmd.name:
                    color = colors.get('color1')
                if 'lid' in cmd.name:
                    my_offset += 4
                if 'pre disp' in cmd.name:
                    my_offset += 8
                if '37C' in cmd.name:
                    my_offset += 4
                    color = colors.get(color_map['incu'])
            if source == 'wait':
                my_width = 7
            if source == 'idle':
                my_width = 7
            if source == 'run':
                continue
            width *= 2
            my_width *= 2
            my_offset *= 2
            if (est := e.metadata.est) and (dur := e.duration):
                pct = round(100 * dur / est, 1)
            else:
                pct = 100.0
            for_show = pbutils.nub(e) | dict(
                t=pbutils.pp_secs(t),
                t0=pbutils.pp_secs(t0),
                machine=machine,
                source=source,
                est=pbutils.pp_secs(e.metadata.est or 0.0),
                duration=pbutils.pp_secs(e.duration or 0.0),
                id=e.metadata.id,
                pct=pct,
                stage=e.metadata.stage,
                thread_resource=m.thread_resource,
            )
            area += div(
                (m.plate_id if t - t0 > 9.0 and my_width > 4 else '') or '',
                css='''
                    position: absolute;
                    border-radius: 2px;
                    border: 1px #0005 solid;
                    display: grid;
                    place-items: center;
                    font-size: 12px;
                    background: var(--bg-color);
                    cursor: pointer;
                    filter: contrast(1.3);
                    text-align: center;
                ''',
                css__=f'''
                    --bg-color: {color};
                    --fg-color: {fg_color};
                ''',
                style=
                    f'''
                        left: {slot * width + my_offset:.1f}px;
                        width: {my_width - 2:.1f}px;
                        top: {zoom * t0:.1f}px;
                        height: {max(zoom * (t - t0), 1):.1f}px;
                        min-height: 5px;
                    '''
                    if vertical.value else
                    f'''
                        top: {slot * width + my_offset:.1f}px;
                        height: {my_width - 2:.1f}px;
                        left: {20 + zoom * t0:.1f}px;
                        width: {max(zoom * (t - t0), 1):.1f}px;
                        min-width: 5px;
                    '''
                ,
                css_=
                    '''
                        &:hover::after {
                            position: absolute;
                            display: block;
                            left: 100%;
                            top: 0;
                            margin-left: 5px;
                            content: attr(shortinfo);
                        }
                        &:hover {
                            z-index: 10;
                        }
                    '''
                    if vertical.value else
                    '''
                        &:hover::after {
                            position: absolute;
                            display: block;
                            height: 100%;
                            top: 100%;
                            content: attr(shortinfo);
                        }
                        &:hover {
                            z-index: 10;
                        }
                    ''',
                shortinfo=str(e.cmd) if vertical.value else str(e.duration),
                css___='outline: 2px #f00a dashed; border-radius: 0;' if pct > 101 else '',
                data_color=color,
                data_fg_color=fg_color,
                data_info=pbutils.show(for_show, use_color=False),
                data_short_info=pbutils.show(e.cmd, use_color=False),
                onclick='''
                    console.log('%c' + this.dataset.info, `color: ${this.dataset.fgColor}; background: ${this.dataset.color}`)
                ''',
                ondblclick='event.preventDefault();' + call(delay_ids.assign, str(m.id)),
                oncontextmenu='event.preventDefault();' + call(delay_ids.assign, str(m.id)),
            )

        yield area


