from __future__ import annotations
from typing import Iterator, Any, cast, Callable
from typing import Literal

from .utils.viable import serve, div, pre, Node, js, call
from .utils.viable.provenance import store, Var
from .utils import viable as V
from .utils import curl, post_json
from .utils import humanize_time
from .utils import serializer
from .utils.mixins import DBMixin, DB, Meta

from .env import Env
from .execute import QueueItem, FridgeSlot, Checkpoint, FridgeOccupant
from .commands import Command
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
from pathlib import Path

from . import protocols
from .protocols import FromHotelTodo, FromFridgeTodo

import csv

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

def enqueue(cmds: list[Command], where: Literal['first', 'last'] = 'last'):
    with Env.make(sim=not live) as env:
        execute.enqueue(env, cmds, where=where)

def enqueue_todos(todos: list[FromHotelTodo], thaw_secs: float=0):
    cmds = protocols.image_todos_from_hotel(todos, thaw_secs)
    enqueue(cmds)

def make_hts_files(todos: list[tuple[str, FromFridgeTodo]]) -> list[FromFridgeTodo]:
    out: list[FromFridgeTodo] = []
    for rel, todo in todos:
        full = modify_hts_file(rel, todo.base_name)
        out += [todo.replace(hts_full_path=full)]
    return out

def enqueue_plates_with_metadata(plates: list[tuple[str, PlateMetadata]], thaw_secs: float=0):
    todos: list[FromHotelTodo] = []
    for hotel_loc, plate in plates:
        full = modify_hts_file(plate.hts_file, plate.base_name)
        todos += [
            FromHotelTodo(
                hotel_loc=hotel_loc,
                plate_id='',
                hts_full_path=full,
            )
        ]
    enqueue_todos(todos, thaw_secs)

def modify_hts_file(hts_file_rel: str, base_name: str):
    project = str(Path(hts_file_rel).parent)
    res = post_json(f'{IMX_URL}/dir_list', {
        'cmd': 'hts_mod',
        'path': hts_file_rel,
        'experiment_set': project,
        'experiment_base_name': base_name,
    })
    return res['value']['full']

from typing import Literal

def modify_queue(item: QueueItem, action: Literal['restart', 'remove']):
    with Env.make(sim=not live) as env:
        with env.db.transaction:
            assert item == item.reload(env.db) # possible race with handling this item
            if action == 'restart':
                item.replace(started=None, finished=None, error=None).save(env.db)
            elif action == 'remove':
                if item.started:
                    item.replace(finished=datetime.now(), error=None).save(env.db)
                else:
                    item.replace(started=datetime.now(), finished=datetime.now(), error=None).save(env.db)

def clear_queue():
    with Env.make(sim=not live) as env:
        with env.db.transaction:
            for item in env.db.get(QueueItem).where(finished=None):
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
                {call(modify_queue, item, "restart")};
            else if (window.confirm(`Remove command? (item: ${{this.dataset.item}})`))
                {call(modify_queue, item, "remove")};
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
            done = env.db.get(QueueItem).order(by='finished').where_not(finished=None).list()
            yield queue_table([*done[-10:], *todo])
        yield V.queue_refresh(300)

    if page.value == 'queue':
        with Env.make(sim=not live) as env:
            items = env.db.get(QueueItem).order(by='pos').where(finished=None)
            yield queue_table(items)
        yield V.queue_refresh(300)

        if items:
            yield V.button(
                'clear queue',
                onclick='window.confirm("really?") && ' + call(clear_queue)
            )

    if page.value == 'log':
        with Env.make(sim=not live) as env:
            items = env.db.get(QueueItem).order(by='finished').where_not(finished=None).list()
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
        todos: list[FromHotelTodo] = []

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
                        todos += [FromHotelTodo(hotel, plate_id.value, hts.full)]

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
                        (call(enqueue_todos, todos, thaw_secs=thaw_secs) + '\n;' + store.update(page, 'queue').goto())
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
                PlateMetadata(
                    base_name=row['base_name'],
                    hts_file=row['hts_file'],
                )
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
        plates_todo: list[tuple[str, PlateMetadata]] = []

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
                        plates_todo += [(hotel, plate)]
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
                        (call(enqueue_plates_with_metadata, plates_todo, thaw_secs=thaw_secs) + '\n;' + store.update(page, 'queue').goto())
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

    if page.value == 'image-from-fridge':
        paste = store.str(name='paste')
        desc = '''
            Paste csv with fields "project", "barcode", "base_name" and "hts_file" (relative to 384 well protocol root).
            Other fields are allowed but will be ignored.
            The plates need to already be in the fridge.
            The plates will be imaged in the order specified here.
        '''
        desc = textwrap.dedent(desc).strip()
        yield div(V.p(desc.strip().splitlines()[0]), padding='0px 10px', margin_top='10px')
        yield div(paste.textarea().extend(
            placeholder=desc,
            rows='20',
            cols='100',
            spellcheck='false',
        ))
        with Env.make(sim=not live) as env:
            with env.db.transaction:
                lines: list[str] = ['project,barcode,base_name,hts_file']
                for slot in env.db.get(FridgeSlot):
                    if slot.occupant and slot.occupant.project == 'fridge-test':
                        barcode = slot.occupant.barcode
                        barcode = re.sub('[(].*?[)]', '', barcode)
                        barcode = re.sub('[^0-9]', '', barcode)
                        name = f'test-{barcode}'
                        lines += [f'{slot.occupant.project},{slot.occupant.barcode},{name},fridge-test/short protocol.hts']
                    elif slot.occupant:
                        lines += [f'{slot.occupant.project},{slot.occupant.barcode},,']
        examples = {
            'protac': '''
                project,barcode,base_name,hts_file
                protac35,(384)P000314,protac35-v1-FA-P000314-U2OS-24h-P1-L1,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
                protac35,(384)P000317,protac35-v1-FA-P000317-U2OS-24h-P2-L2,protac35/protac35-v1-FA-BARCODE-U2OS-24h.HTS
                protac35,(384)P000315,protac35-v1-GR-P000315-U2OS-24h-P1-L1,protac35/protac35-v1-GR-BARCODE-U2OS-24h.HTS
                protac35,(384)P000318,protac35-v1-GR-P000318-U2OS-24h-P2-L2,protac35/protac35-v1-GR-BARCODE-U2OS-24h.HTS
            ''',
            'fridge-test': '''
                project,barcode,base_name,hts_file
                fridge-test,(384)P000008,fridge-short-test-1,fridge-test/short protocol.hts
                fridge-test,(384)P000008,fridge-short-test-2,fridge-test/short protocol.hts
                fridge-test,(384)P000008,fridge-short-test-3,fridge-test/short protocol.hts
                fridge-test,(384)P000008,fridge-short-test-4,fridge-test/short protocol.hts
            ''',
            'fridge-contents': '\n'.join(lines),
        }
        examples = {k: textwrap.dedent(v).strip() for k, v in examples.items()}
        yield div(
            V.button('clear', onclick=store.update(paste, '').goto()),
            *[
                V.button(f'load example {k}', onclick=store.update(paste, v).goto())
                for k, v in examples.items()
            ]
        )
        data = parse_csv(paste.value)
        if not data:
            return
        keys = data[0].keys()
        ok = True
        htss = {hts.path.lower(): hts for hts in get_htss()}
        errors: list[str] = []
        fridge_todo: list[tuple[str, FromFridgeTodo]] = []
        with Env.make(sim=not live) as env:
            for i, row in enumerate(data, start=1):
                my_errors: list[str] = []
                fields = 'project barcode base_name hts_file'.split()
                trimmed = {
                    k: (v if isinstance(v := row.get(k), str) else '')
                    for k in fields
                }
                project, barcode, base_name, hts_file = trimmed.values()
                for k, v in trimmed.items():
                    if not v:
                        my_errors += [f'Missing value for {k}']
                if project and barcode:
                    occupant = FridgeOccupant(project=project, barcode=barcode)
                    occs = env.db.get(FridgeSlot).where(occupant=occupant)
                    if len(occs) == 0:
                        my_errors += [f'Barcode not in fridge']
                    elif len(occs) > 1:
                        my_errors += [f'Barcode duplicated in fridge']
                hts = htss.get(hts_file.lower())
                if hts_file and not hts:
                    my_errors += [f'File {hts_file!r} not found']
                if hts:
                    title = f'{hts.full}\nlast modified: {str(hts.ts)} ({humanize_time.naturaldelta(hts.age)} ago)'
                    hts_info = div(hts.path, title=title, data_title=title, cursor='pointer', onclick='alert(this.dataset.title)')
                if my_errors:
                    desc = row.get('barcode', row.get('base_name', ''))
                    if desc:
                        desc = f' ({desc})'
                    errors += [
                        f'Row {i}{desc}:',
                        *['  ' + err for err in my_errors]
                    ]
                if hts:
                    fridge_todo += [(hts.path, FromFridgeTodo(
                        plate_project=project,
                        plate_barcode=barcode,
                        base_name=base_name,
                        hts_full_path='error: must run make_hts_files first',
                    ))]

        pop_delay_hours = store.str('0')
        min_thaw_hours = store.str('0')

        try:
            pop_delay_secs = float(pop_delay_hours.value) * 3600
        except:
            pop_delay_secs = 0.0
            errors += ['Enter a valid number of pop delay hours']

        try:
            min_thaw_secs = float(min_thaw_hours.value) * 3600
        except:
            min_thaw_secs = 0.0
            errors += ['Enter a valid number of min thaw hours']

        yield V.pre(
            '\n'.join(errors),
            color='var(--red)',
            padding='10px',
        )
        ok = not errors

        yield V.div(
            dict(
                css='''
                    & div {
                        margin-bottom: 10px;
                    }
                '''
            ),
            V.div(
                div(V.label('delay from imx start acquire to take out next plate (hours):', pop_delay_hours.input()), align='right', ),
                div(V.label('minimum time in room temperature before acquire (hours):', min_thaw_hours.input()), align='right', ),
            ),
            V.div(
            V.button('add to queue',
                onclick=
                    (
                        call(lambda:
                                enqueue(
                                    protocols.image_from_fridge(
                                        make_hts_files(fridge_todo),
                                        pop_delay_secs=pop_delay_secs,
                                        min_thaw_secs=min_thaw_secs,
                                    )
                                ))
                            + ';\n' +
                        store.update(page, 'queue-and-log').goto()
                    )
                    if ok else '',
                disabled=not(ok),
                title='\n'.join(errors),
                ),
                align='center',
            ),
            width='fit-content',
        )

    if page.value == 'system':
        yield V.div(
            dict(
                css='''
                    & > * {
                        border: 1px #fff2 solid;
                        padding: 5px;
                        margin-top: 5px;
                    }
                    & > * > * { margin: 5px; }
                    & { width: fit-content; }
                '''
            ),
            V.div(
                V.span('test-comm:'),
                V.button(
                    'Test communication with robotarm, barcode reader, imx and fridge.',
                    onclick=
                        call(enqueue, protocols.test_comm(), where='first') + '\n;' +
                        store.update(page, 'queue-and-log').goto()
                ),
            ),
            V.div(
                V.span('Robotarm:'),
                V.button(
                    'restart',
                    onclick=call(enqueue, protocols.home_robot(), where='first')
                ),
                V.button(
                    'start freedrive',
                    onclick=call(enqueue, protocols.start_freedrive(), where='first')
                ),
                V.button(
                    'stop freedrive',
                    onclick=call(enqueue, protocols.stop_freedrive(), where='first')
                ),
            ),
            V.div(
                V.span('Fridge:'),
                V.button(
                    'restart',
                    onclick=call(enqueue, protocols.reset_and_activate_fridge(), where='first')
                ),
            ),
            V.div(
                V.span('Queue processing:'),
                V.button(
                    'Pause',
                    onclick=(
                        call(enqueue, protocols.pause(), where='first') + '\n;' +
                        store.update(page, 'queue-and-log').goto()
                    )
                ),
                V.span('(resume by removing pause from queue)', opacity='0.85'),
            )
        )

    if page.value == 'fridge':
        with Env.make(sim=not live) as env:
            with env.db.transaction:
                slots = env.db.get(FridgeSlot).order(by='occupant').list()
        project_name= store.str()
        num_plates = store.int()
        store.assign_names(locals())
        ok = project_name.value and (1 <= num_plates.value <= 12)
        yield div(
            div('Load plates from hotel', color='var(--green)'),
            div('Place plates in hotel positions H1, H2, ...'),
            div(V.label('project name:',     project_name.input().extend(spellcheck='false')), align='right'),
            div(V.label('number of plates:', num_plates.input()),                              align='right'),
            V.button('load',
                onclick=(
                    call(
                        enqueue,
                        protocols.load_fridge(project_name.value, num_plates.value)
                    ) + ';\n' +
                        store.update(page, 'queue-and-log').goto()
                ) if ok else '',
                disabled=not ok,
            ),
            border='1px #fff1 solid',
            padding='8px',
            margin='20px 0',
            css='& > * {padding: 4px}',
            width='fit-content',
        )
        tbl = V.table(css='''
            & td, & th {
                padding: 3px 8px;
                border: 1px #fff2 solid;
            }
        ''')
        tbl += V.tr(*map(V.th, 'location project barcode'.split()))
        for slot in slots:
            tbl += V.tr(
                V.td(slot.loc),
                V.td(slot.occupant.project if slot.occupant else ''),
                V.td(slot.occupant.barcode if slot.occupant else ''),
            )
        yield tbl
        yield V.queue_refresh(after_ms=1000)

@serve.route()
def index():

    pages = '''
        -image-from-hotel-using-metadata
        -plate-metadata
        -image-from-hotel-v1
        system
        fridge
        image-from-fridge
        queue
        -queue-and-log
        log
    '''.split()

    with store.query:
        page = store.str(default=pages[0], name='page')

    yield V.head(V.title(f'imx imager scheduler gui - {page.value}'))
    yield {'sheet': sheet}

    nav = div(css='&>* {margin: 20px 10px}')
    hidden = V.select(
        V.option('more methods...', value=''),
        onchange=store.update(page, js('this.selectedOptions[0].value')).goto()
    )

    for p in pages:
        if p.startswith('-'):
            po = p.removeprefix('-')
            hidden += V.option(
                p.replace('-', ' '),
                value=po,
                color='var(--yellow)' if page.value == po else '',
            )
        else:
            nav += V.button(
                p.replace('-', ' '),
                onclick=store.update(page, p).goto(),
                color='var(--yellow)' if page.value == p else '',
            )

    nav += hidden
    yield nav

    with store.db:
        with store.sub(page.value.replace('-', '')):
            yield from index_page(page)
def main():
    print('main', __name__)
    serve.run(port=5051)

if __name__ == '__main__':
    main()
