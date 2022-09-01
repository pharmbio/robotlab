from __future__ import annotations
from typing import Iterator, Any, cast

from .utils.viable import serve, esc, div, pre, Node, js
from .utils.viable.provenance import store, Var
from .utils import viable as V
from .utils import curl
from .utils import humanize_time
from .utils.mixins import DBMixin, DB

from .env import Env
from .execute import QueueItem, FridgeSlot, Checkpoint
from . import execute
from . import commands as cmds

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pprint import pp
from threading import Lock
import platform
import time
import sys
import re

from .protocols import Todo, image_todos_from_hotel

serve.suppress_flask_logging()

live = '--live' in sys.argv

IMX_URL = 'http://10.10.0.99:5000'
if platform.node() == 'halvdan':
    IMX_URL = 'http://127.0.0.1:5099'

@dataclass(frozen=True)
class HTS:
    path: str
    full: str
    ts: datetime
    @property
    def age(self) -> timedelta:
        return datetime.now() - self.ts

_get_htss_lock = Lock()

@lru_cache(maxsize=1)
def _get_htss(time: int):
    data = curl(f'{IMX_URL}/dir_list/list')
    print(time, data['success'], data.keys())
    if not data['success']:
        pp(data)
    htss: list[HTS] = [HTS(h['path'], h['full'], datetime.fromisoformat(h['modified'])) for h in data['value']]
    htss: list[HTS] = list(reversed(sorted(htss, key=lambda hts: hts.path)))
    return htss

def get_htss():
    with _get_htss_lock:
        return _get_htss(round(time.monotonic() / 10) * 10)

sheet = '''
    *, *::before, *::after {
        box-sizing: border-box;
    }
    * {
        margin: 0;
    }
    html, body {
        height: 100%;
    }
    html {
        color:      var(--fg);
        background: var(--bg);
        font-size: 16px;
        font-family: Consolas, monospace;
        letter-spacing: -0.025em;
    }
    * {
        color: inherit;
        background: inherit;
        font-size: inherit;
        font-family: inherit;
        letter-spacing: inherit;
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
    input {
        border: 1px #0003 solid;
        border-right-color: #fff2;
        border-bottom-color: #fff2;
    }
    button {
        border-width: 1px;
    }
    input, button, select {
        padding: 8px;
        border-radius: 2px;
        background: var(--bg);
        color: var(--fg);
    }
    button:disabled {
        opacity: 60%;
    }
    select {
        width: 100%;
        padding-left: 4px;
    }
    input:focus-visible, button:focus-visible, select:focus-visible {
        outline: 2px  var(--blue) solid;
        outline-color: var(--blue);
    }
    input:hover {
        border-color: var(--blue);
    }
    body {
        width: 900px;
        margin: 0 auto;
    }
'''

@serve.expose
def enqueue_todos(todos: list[Todo], thaw_secs: float=0):
    cmds = image_todos_from_hotel(todos, thaw_secs=thaw_secs)
    with Env.make(sim=not live) as env:
        execute.enqueue(env, cmds)

from typing import Literal

@serve.expose
def modify(item: QueueItem, action: Literal['restart', 'remove']):
    with Env.make(sim=not live) as env:
        if action == 'restart':
            item.replace(started=None, finished=None, error=None).save(env.db)
        elif action == 'remove':
            if item.started:
                item.replace(finished=datetime.now(), error=None).save(env.db)
            else:
                item.replace(started=datetime.now(), finished=datetime.now(), error=None).save(env.db)

def queue_table(items: list[QueueItem]):
    grid = div(
        padding_top='20px',
        display='grid',
        grid_template_columns='auto 150px auto 1fr',
        grid_gap='0 10px',
        align_items='top',
    )
    now = datetime.now()
    for item in items:
        if item.finished:
            assert item.started
            grid += V.div(f'{item.finished.replace(microsecond=0)}')
            dur = f'({humanize_time.naturaldelta(item.finished - item.started)})'
            grid += V.div(dur)
        elif item.started:
            grid += V.div(f'{item.started.replace(microsecond=0)}')
            if not item.error:
                since = f'(for {humanize_time.naturaldelta(now - item.started)})'
                grid += V.div(since)
            else:
                grid += V.div()
        else:
            grid += V.div(str(item.pos))
            grid += V.div()

        purge = f'''
            if (this.dataset.started && window.confirm(`Rerun command? (item: ${{this.dataset.item}})`))
                {modify.call(item, "restart")};
            else if (window.confirm(`Remove command? (item: ${{this.dataset.item}})`))
                {modify.call(item, "remove")};
        '''
        if item.finished:
            purge=''

        grid += V.div(
            item.cmd.__class__.__name__,
            data_item=str(item),
            data_started=bool(item.started),
            onclick=purge,
            cursor=purge and 'pointer',
        )
        args = [str(a) for a in item.cmd.__dict__.values()]
        args = [re.sub(r'.*384-Well_Plate_Protocols\\', '', a) for a in args]
        grid += V.div(', '.join(args))
        if item.error:
            grid += V.pre(
                item.error, color='var(--red)', grid_column='1 / -1',
                data_item=str(item),
                data_started=bool(item.started),
                onclick=purge,
                cursor='pointer',
            )
    return grid

@serve.route()
def index():

    pages = '''
        image-from-hotel
        queue-and-log
        queue
        log
    '''.split()

    with store.query:
        page = store.str(default=pages[0], name='page')

    yield V.head(V.title(f'imx imager scheduler gui - {page.value}'))
    yield {'sheet': sheet}

    nav = div(css='&>* {margin: 20px 10px}')

    for p in pages:
        nav += V.button(
            p.replace('-', ' '),
            onclick=store.update(page, p).goto(),
            color='var(--yellow)' if page.value == p else '',
        )

    yield nav

    if page.value == 'queue-and-log':
        with Env.make(sim=not live) as env:
            todo = env.db.get(QueueItem).order(by='pos').limit(10).where(finished=None)
            done = env.db.get(QueueItem).order(by='finished').where_str('value ->> "finished" is not null')
            yield queue_table([*done[-10:], *todo])
        yield V.queue_refresh(300)

    if page.value == 'queue':
        with Env.make(sim=not live) as env:
            items = env.db.get(QueueItem).order(by='pos').where(finished=None)
            yield queue_table(items)
        yield V.queue_refresh(300)

    if page.value == 'log':
        with Env.make(sim=not live) as env:
            items = env.db.get(QueueItem).order(by='finished').where_str('value ->> "finished" is not null')
            items = list(reversed(items))
            yield queue_table(items)
        yield V.queue_refresh(300)

    if page.value == 'image-from-hotel':

        htss = {hts.path: hts for hts in get_htss()}
        datalist  = V.datalist(id='htss', width='800px')
        for _, hts in htss.items():
            datalist += V.option(value=hts.path)
        yield datalist

        grid = div(padding_top='20px', display='grid', grid_template_columns='50px 200px 1fr 40px', align_items='center')

        grid += div()
        grid += div('plate_id', justify_self='center')
        grid += div('hts path', justify_self='center')
        grid += div()

        errors: list[str] = []
        todos: list[Todo] = []

        with store.db:
            hotels = list(reversed([i + 1 for i in range(11)]))
            for i, hotel_pos in enumerate(hotels):
                hotel = f'H{hotel_pos}'
                with store.sub(hotel):
                    plate_id = store.str(name='plate_id')
                    path = store.str(name='path')
                    hts = htss.get(path.value)
                    grid += div(hotel + ':', justify_self='right')
                    grid += plate_id.input().extend(margin='5px', padding='5px', tabindex=str(i+1), spellcheck='false')
                    grid += path.input().extend(list='htss', width='auto', font_family='monospace', margin='5px', padding='5px', tabindex=str(i+1+len(hotels)), spellcheck='false')
                    if not hts and path.value:
                        grid += div('?', color='var(--red)', title=f'Unknown path {path.value!r}')
                        errors += [f'Path not ok on {hotel}']
                    elif hts:
                        title=f'{hts.full}\nlast modified: {str(hts.ts)} ({humanize_time.naturaldelta(hts.age)} ago)'
                        grid += V.label('ok!', color='var(--green)', title=title, data_title=title, cursor='pointer', onclick='alert(this.dataset.title)')
                    else:
                        grid += div()
                    print(i, hotel, repr(plate_id.value), repr(hts and hts.path), sep='\t')
                    if hts and not plate_id.value:
                        errors += [f'No plate id on {hotel}']
                    if plate_id.value and not path.value:
                        errors += [f'No path on {hotel}']
                    if plate_id.value and hts:
                        todos += [Todo(hotel, plate_id.value, hts.full)]

        if not todos:
            errors += ['Nothing to do']

        error = ',\n'.join(errors)

        yield grid

        enabled = not error and todos

        thaw_secs = store.int(0, name='thaw_secs')

        yield V.div(
            V.div(
                V.label(
                    'initial thaw delay (secs):',
                    thaw_secs.input(),
                ),
                V.button(
                    'clear',
                    margin_top='20px',
                    onclick=store.defaults.goto(),
                ),
                V.button(
                    'add to queue',
                    margin_top='20px',
                    disabled=not enabled,
                    title=error,
                    onclick=
                        (enqueue_todos.call(todos) + '\n;' + store.update(page, 'queue').goto())
                        if enabled else
                        ''
                ),
                css='''& > * {
                    margin-left: 10px;
                    min-width: 100px;
                    margin-top: 20px;
                    padding: 10px 20px;
                }''',
            ),
            display='grid',
            place_items='center right',
        )

def main():
    print('main', __name__)
    serve.run(port=5051)

if __name__ == '__main__':
    main()
