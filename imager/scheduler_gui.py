from __future__ import annotations
from typing import Iterator, Any, cast, Callable

from .utils.viable import serve, esc, div, pre, Node, js
from .utils.viable.provenance import store, Var
from .utils import viable as V
from .utils import curl, post_json
from .utils import humanize_time
from .utils import serializer
from .utils.mixins import DBMixin, DB, Meta

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
import textwrap

from .protocols import Todo, image_todos_from_hotel

import csv

from .utils.freeze_function import FrozenFunction
from inspect import signature

@serve.expose
def call_saved(f: FrozenFunction, *args: Any, **kws: Any) -> Any:
    res = f.thaw()(*args, **kws)
    if isinstance(res, dict):
        return {'refresh': True} | res
    else:
        return {'refresh': True}

def call(f: Callable[..., Any], *args: Any | js, **kws: Any | js) -> str:
    # apply any defaults to the arguments now so that js fragments get evaluated
    s = signature(f)
    b = s.bind(*args, **kws)
    b.apply_defaults()
    return call_saved.call(FrozenFunction.freeze(f), *b.args, **b.kwargs)

def parse_csv(s: str):
    try:
        niff = csv.Sniffer()
        dialect = niff.sniff(s)
    except:
        dialect = None
    if dialect:
        reader = csv.DictReader(s.splitlines(), dialect=dialect)
        return list(reader)

serve.suppress_flask_logging()

live = '--live' in sys.argv

IMX_URL = 'http://10.10.0.99:5050'
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

def mod_hts(hts_file: str, todo: str):
    return post_json(f'{IMX_URL}/dir_list', {
        'cmd': 'mod_hts',
        'path': hts_file,
        'experiment_set': todo,
        'experiment_base_name': todo,
    })

@lru_cache(maxsize=1)
def _get_htss(time: int):
    data = curl(f'{IMX_URL}/dir_list/list')
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
        width: 1100px;
        margin: 0 auto;
    }
'''

@serve.expose
def enqueue_todos(todos: list[Todo], thaw_secs: float=0):
    cmds = image_todos_from_hotel(todos, thaw_secs)
    with Env.make(sim=not live) as env:
        execute.enqueue(env, cmds)

@serve.expose
def enqueue_plates_with_metadata(plates: list[PlateMetadata], thaw_secs: float=0):
    pass

from typing import Literal

@serve.expose
def modify_queue(item: QueueItem, action: Literal['restart', 'remove']):
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
                {modify_queue.call(item, "restart")};
            else if (window.confirm(`Remove command? (item: ${{this.dataset.item}})`))
                {modify_queue.call(item, "remove")};
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

@dataclass(frozen=True)
class TodoV2:
    hotel_loc: str  # 'H1'
    plate_id: str
    hts_path: str

@dataclass(frozen=True)
class PlateMetadata(DBMixin):
    base_name: str = ''
    hts_file: str = ''
    id: int = -1
    __meta__ = Meta(log=True)

serializer.register(globals())

from flask import after_this_request,  g
from flask.wrappers import Response
from werkzeug.local import LocalProxy

def get_plate_db() -> DB:
    if not g.get('plate_db'):
        g.plate_db = db = DB.connect('plate.db')
        @after_this_request
        def _close_db(response: Response) -> Response:
            db.con.close()
            del g.plate_db
            return response
    return g.plate_db

plate_db: DB = LocalProxy(get_plate_db) # type: ignore

# should add a unique index on base name ...

def plate_metadata_table(data: list[PlateMetadata], with_remove: bool=True, check_duplicates: bool=False):
    with DB.open('plate.db') as db:
        htss = {hts.path.lower(): hts for hts in get_htss()}
        table = V.table(css='& td, & tr {background: var(--bg-bright); padding: 5px}')
        all_ok = True
        for row in data:
            base_td = V.td(row.base_name)
            hts_td = V.td(row.hts_file)
            hts = htss.get(row.hts_file.lower())
            if check_duplicates:
                dups = db.get(PlateMetadata).where(base_name=row.base_name)
                if dups:
                    title=f'{row.base_name} already in database as\n{" and ".join(map(str, dups))}'
                    base_td = base_td.extend(
                        color='var(--red)', title=title, data_title=title, cursor='pointer', onclick='alert(this.dataset.title)'
                    )
                    all_ok = False
                else:
                    title=f'base name ok'
                    base_td = base_td.extend(title=title)
            if hts:
                title = f'{hts.full}\nlast modified: {str(hts.ts)} ({humanize_time.naturaldelta(hts.age)} ago)'
                hts_td = hts_td.extend(title=title, data_title=title, cursor='pointer', onclick='alert(this.dataset.title)')
            else:
                hts_td = hts_td.extend(title='file not found', color='var(--red)')
                all_ok = False
            tr = V.tr(base_td, hts_td)
            if with_remove:
                tr += V.td(V.button(
                    'remove',
                    padding='2px 8px',
                    css='''
                        &:hover { border-color: var(--red); }
                        & { border-color: #0000; }
                    ''',
                    onclick=call(lambda: row.delete(plate_db)),
                ))
            table += tr
        return table, all_ok

def index_page(page: Var[str]):
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

    if page.value == 'image-from-hotel-v1':
        htss = {hts.path.lower(): hts for hts in get_htss()}
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
                    hts = htss.get(path.value.lower())
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
                    if plate_id.value or path.value:
                        print(i, hotel, repr(plate_id.value), repr(hts and hts.path), sep='\t')
                    if hts and not plate_id.value:
                        errors += [f'No plate id on {hotel}']
                    if plate_id.value and not path.value:
                        errors += [f'No path on {hotel}']
                    if plate_id.value and hts:
                        todos += [Todo(hotel, plate_id.value, hts.full)]

        thaw_hours = store.str('0', name='thaw_hours')

        try:
            thaw_secs = float(thaw_hours.value) * 3600
        except:
            thaw_secs = 0.0
            errors += ['Enter a valid number of hours']


        if not todos:
            errors += ['Nothing to do']

        error = ',\n'.join(errors)

        yield grid

        enabled = not error and todos

        yield V.div(
            V.div(
                V.label(
                    'initial thaw delay (hours):',
                    thaw_hours.input(),
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
                        (enqueue_todos.call(todos, thaw_secs=thaw_secs) + '\n;' + store.update(page, 'queue').goto())
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

    if page.value == 'plate-metadata':
        paste = store.str(name='paste')
        yield div('paste csv:', padding='0px 10px', margin_top='10px')
        yield div(paste.textarea().extend(
            placeholder='Paste csv with fields "base_name" and "hts_file" (relative to 384 well protocol root)',
            rows='8',
            cols='100',
            spellcheck='false',
        ))
        example1 = '''
            base_name,hts_file
            protac35-v1-FA-P12340314-U2OS-24h-P1-L1,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
            protac35-v1-FA-P12340317-U2OS-24h-P2-L2,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
            protac35-v1-GR-P12340315-U2OS-24h-P1-L1,protac35/protac35-v1-GR-BARCODE-U2OS-24h.HTS
            protac35-v1-GR-P12340318-U2OS-24h-P2-L2,protac35/protac35-v1-GR-BARCODE-U2OS-24h.HTS
        '''
        example2 = '''
            base_name,hts_file
            fridge-short-test-1,fridge-test/short protocol.hts
            fridge-short-test-2,fridge-test/short protocol.hts
            fridge-short-test-3,fridge-test/short protocol.hts
            fridge-short-test-4,fridge-test/short protocol.hts
        '''
        example1 = textwrap.dedent(example1).strip()
        example2 = textwrap.dedent(example2).strip()
        yield div(
            V.button('clear', onclick=store.update(paste, '').goto()),
            V.button('load example 1', onclick=store.update(paste, example1).goto()),
            V.button('load example 2', onclick=store.update(paste, example2).goto()),
        )
        yield div('csv contents:', padding='0px 10px', margin_top='40px')
        data = parse_csv(paste.value)
        if data:
            keys = data[0].keys()
            ok = True
            if 'id' in keys:
                yield div(f'Field "id" not allowed (csv has: {", ".join(keys)})', color='var(--red)')
                ok = False
            for key in 'base_name hts_file'.split():
                if key not in keys:
                    yield div(f'Field {key} not provided (csv has: {", ".join(keys)})', color='var(--red)')
                    ok = False
            plates = [
                PlateMetadata(**row)
                for row in data
            ]
            table, ok = plate_metadata_table(plates, with_remove=False, check_duplicates=True)
            yield table
            yield V.button('add to database',
                onclick=call(lambda: [plate.save(plate_db) for plate in plates]),
                disabled=not(ok)
            )
        yield div('database contents:', padding='0px 10px', margin_top='40px')
        with DB.open('plate.db') as db:
            table, ok = plate_metadata_table(db.get(PlateMetadata).order(by='base_name').where())
            yield table

    if page.value == 'image-from-hotel-using-metadata':
        # htss = {hts.path: hts for hts in get_htss()}

        datalist  = V.datalist(id='base_names', width='800px')
        with DB.open('plate.db') as db:
            plates = db.get(PlateMetadata).order(by='base_name').where()
        for plate in plates:
            datalist += V.option(value=plate.base_name)
        plates_by_base_name = {plate.base_name: plate for plate in plates}
        yield datalist

        grid = div(padding_top='20px', display='grid', grid_template_columns='50px 1fr 1fr', align_items='center',
            css='''
                & > input {
                    padding: 5px;
                    margin: 5px;
                }
                & > input[error] {
                    outline-color: var(--red);
                    border-color: var(--red);
                }
            ''')

        grid += div()
        grid += div('base_name', justify_self='center')
        grid += div('hts_file', justify_self='center')

        errors: list[str] = []
        plates_todo: list[PlateMetadata] = []

        with store.db:
            hotels = list(reversed([i + 1 for i in range(11)]))
            for i, hotel_pos in enumerate(hotels):
                my_errors: list[str] = []
                hotel = f'H{hotel_pos}'
                with store.sub(hotel):
                    base_name = store.str()
                    grid += div(hotel + ':', justify_self='right')
                    grid += base_name.input().extend(list='base_names', tabindex='1', spellcheck='false')
                    plate = plates_by_base_name.get(base_name.value)
                    if plate:
                        grid += div(plate.hts_file)
                        plates_todo += [plate]
                    elif base_name.value:
                        grid += div('base name not in database', color='var(--red)')
                        errors += [f'base name {base_name.value!r} not in database']
                    else:
                        grid += div()

                    errors += [hotel + ': ' + error for error in my_errors]

        thaw_hours = store.str('0', name='thaw_hours')

        try:
            thaw_secs = float(thaw_hours.value) * 3600
        except:
            thaw_secs = 0.0
            errors += ['Enter a valid number of hours']


        if not plates_todo:
            errors += ['Nothing to do']

        error = ',\n'.join(errors)

        yield grid

        enabled = not error and plates_todo


        yield V.div(
            V.div(
                V.label(
                    'initial thaw delay (hours):',
                    thaw_hours.input(),
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
                        (enqueue_plates_with_metadata.call(plates_todo, thaw_secs=thaw_secs) + '\n;' + store.update(page, 'queue').goto())
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

@serve.route()
def index():

    pages = '''
        image-from-hotel-v1
        plate-metadata
        image-from-hotel-using-metadata
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

    with store.db:
        with store.sub(page.value.replace('-', '')):
            yield from index_page(page)
def main():
    print('main', __name__)
    serve.run(port=5051)

if __name__ == '__main__':
    main()
