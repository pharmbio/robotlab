from __future__ import annotations
from typing import Iterator, Any, cast

from .utils.viable import serve, esc, div, pre, Node, js
from .utils.viable.provenance import store, Var
from .utils import viable as V
from .utils import curl
from .utils import humanize_time

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pprint import pp
from threading import Lock
import platform
import time

serve.suppress_flask_logging()

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

@dataclass(frozen=True)
class Todo:
    hotel_pos: int
    plate_id: str
    hts: HTS

@serve.route()
def index():
    yield {'sheet': sheet}
    yield V.head(V.title('imx imager scheduler gui'))
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
    todo: list[Todo] = []

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
                    todo += [Todo(hotel_pos, plate_id.value, hts)]

    if not todo:
        errors += ['Nothing to do']

    error = ',\n'.join(errors)

    yield grid

    yield V.div(
        V.div(
            V.button(
                'clear',
                margin_top='20px',
                onclick=store.defaults.goto(),
            ),
            V.button(
                'add to queue',
                margin_top='20px',
                disabled=bool(len(error)),
                title=error,
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
