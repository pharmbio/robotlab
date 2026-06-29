from typing import *
from dataclasses import *

from .machine import Machine

from urllib.request import urlopen

@dataclass(frozen=True)
class Shelly(Machine):
    ip: str

    def on(self, max_on_time_secs: None | float = None):
        args = [f'on=true']
        if max_on_time_secs:
            args += [f'toggle_after={max_on_time_secs}']
        self._curl(args)

    def off(self):
        args = [f'on=false']
        self._curl(args)

    def _curl(self, args_list: list[str]):
        args = '&'.join(args_list)
        url = f'http://{self.ip}/rpc/Switch.Set?id=0&{args}'
        self.log(f'curl({url!r})')
        res = None
        try:
            res = urlopen(url, timeout=2.5)
            res = res.read()
        except Exception as e:
            self.log(f'curl({url!r}) error: {e=!r} {e=} {res=}')
            return
        self.log(f'curl({url!r}) = {res}')
