from __future__ import annotations
from typing import Iterator, Any, cast

from .utils.viable import serve, esc, div, pre, Node, js
from .utils.viable.provenance import store, Var
from .utils import viable as V
from .utils import curl

from pprint import pp

import json
import platform
from datetime import datetime, timedelta
from .utils import humanize_time
from dataclasses import dataclass
import re

serve.suppress_flask_logging()

IMX_URL = 'http://10.10.0.99:5000'
if platform.node() == 'halvdan':
    IMX_URL = 'http://127.0.0.1:5099'

@dataclass(frozen=True)
class HTS:
    path: str
    ts: datetime
    @property
    def age(self) -> timedelta:
        return datetime.now() - self.ts

import time
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_htss(time: int):
    data = curl(f'{IMX_URL}/dir_list/list')
    print(time, data['success'], data.keys())
    if not data['success']:
        pp(data)
    htss: list[HTS] = [HTS(h['path'], datetime.fromisoformat(h['modified'])) for h in data['value']]
    htss: list[HTS] = list(reversed(sorted(htss, key=lambda hts: hts.ts)))
    return htss

def get_htss():
    return _get_htss(round(time.monotonic() / 10) * 10)

get_htss()

@serve.route()
def index():
    yield V.title('imx imager scheduler gui')
    htss = get_htss()
    short: dict[str, HTS] = {}
    for hts in htss:
        if hts.age > timedelta(days=3 * 365):
            continue
        root, rest = hts.path.split('/', 1)
        nums: list[str] = re.findall(r'\d+', root)
        if len(nums) == 1:
            short[f'[{nums[0]}] {rest.strip(".HTS")}'] = hts
    datalist  = V.datalist(id='htss', width='800px')
    for k, hts in short.items():
        datalist += V.option(value=k)
    yield datalist
    for i in reversed([i + 1 for i in range(10)]):
        with store.sub(f'h{i}'):
            plate_id = store.str(name='plate_id')
            path = store.str(name='path')
            hts = short.get(path.value)
            yield V.div(
                V.span(f'h{i}', width='50px', display='inline-block'),
                plate_id.input().extend(font_family='monospace', margin='5px', padding='5px', tabindex=str(i)),
                path.input().extend(list='htss', width='600px', font_family='monospace', margin='5px', padding='5px', tabindex=str(10+i)),
                '' if not hts else V.label('ok!', title=f'last modified: {str(hts.ts)} ({humanize_time.naturaldelta(hts.age)} ago), path: {hts.path}')
            )

def main():
    print('main', __name__)
    serve.run(port=5051)

if __name__ == '__main__':
    main()
