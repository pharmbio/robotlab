from __future__ import annotations
from typing import *

from viable import serve, js, store
from viable import Tag, pre, div, span, label

from .log import Log
from . import commands

from collections import *

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
    cmdline_to_log = lru_cache(cmdline_to_log)

    @serve.one('/')
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
        zoom_int = store.query.int(100, min=1, max=1000)
        store.assign_names(locals())
        zoom = zoom_int.value / 100.0
        yield div(
            label(span('cmdline: '), cmdline.input(iff='0').extend(onkeydown='event.key == "Enter" && ' + store.update(cmdline, js('this.value')).goto())),
            label(span('zoom: '), zoom_int.range(), span(str(zoom_int.value))),
            position='sticky',
            top=0,
            background='#fff',
            border_bottom='1px #0008 solid',
            z_index='1' + '0' * 9,
        )

        try:
            entries = cmdline_to_log(cmdline.value)
        except:
            import traceback
            traceback.print_exc()
            yield pre(traceback.format_exc())
            return

        from . import estimates
        if estimates.guesses:
            pbutils.pr(estimates.guesses)

        yield pre('\n'.join(entries.group_durations_for_display()))

        area = div(style=f'''
            width: 100%;
            height: {zoom * max(e.t for e in entries)}px;
        ''', css='''
            position: relative;
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
            if slot is None:
                slot = {
                    'incu': 1,
                    'wash': 2,
                    'disp': 3,
                }.get(machine, 1)
            slot = 2 * slot
            if m.thread_resource in ('wash', 'disp', 'incu'):
                slot += 1
            if source == 'duration':
                slot = 18 + plate
            color_map = {
                'wait': 'color3',
                'idle': 'color3',
                'robotarm': 'color4',
                'wash': 'color6',
                'disp': 'color5',
                'incu': 'color2',
            }
            color = colors.get(color_map.get(source, ''), '#ccc')
            fg_color = '#000'
            if color == colors.get('color4'):
                fg_color = '#fff'
            width = 14
            my_width = 14
            my_offset = 0
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
                duration=pbutils.pp_secs(e.duration or 0.0),
                slot=slot,
                est=e.metadata.est,
                id=e.metadata.id,
                pct=pct,
            )
            area += div(
                str(plate) if t - t0 > 9.0 and my_width > 4 and plate else '',
                css='''
                    position: absolute;
                    border-radius: 2px;
                    border: 1px #0005 solid;
                    display: grid;
                    place-items: center;
                    font-size: 12px;
                    background: var(--bg-color);
                ''',
                css_='''
                    &:hover {
                        z-index: 1;
                    }
                    &:hover::after, &:hover::before {
                        white-space: pre;
                        padding: 2px 4px;
                        border-radius: 2px;
                        border: 1px #0005 solid;
                        background: var(--bg-color);
                        color: var(--fg-color);
                        z-index: 1;
                        font-size: 16px;
                    }
                    &:hover::after {
                        position: fixed;
                        right: 0;
                        bottom: 0;
                        min-width: 40em;
                        min-height: 40em;
                        content: attr(data-info);
                    }
                    &:hoer::before {
                        position: absolute;
                        left: calc(100% + 1px);
                        top: -1px;
                        content: attr(data-short-info);
                    }
                ''',
                css__=f'''
                    --bg-color: {color};
                    --fg-color: {fg_color};
                ''',
                style=f'''
                    left: {slot * width + my_offset:.1f}px;
                    width: {my_width - 2:.1f}px;
                    top: {zoom * t0:.1f}px;
                    height: {max(zoom * (t - t0), 1):.1f}px;
                    min-height: 5px;
                ''',
                css___='outline: 2px #f00a dashed; border-radius: 0;' if pct > 120 else '',
                data_info=pbutils.show(for_show, use_color=False),
                data_short_info=pbutils.show(e.cmd, use_color=False),
            )

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
