from __future__ import annotations

from dataclasses import *
from typing import *

import json
from urllib.request import Request, urlopen

from .moves import Move

@dataclass(frozen=True)
class PF:
    host: str
    port_rw: int = 10100
    port_ro: int = 10000
    timeout_secs: int = 10 * 60

    def _url(self) -> str:
        if self.host.startswith(('http://', 'https://')):
            return self.host.rstrip('/') + '/pf'
        else:
            return f'http://{self.host}:5050/pf'

    def _call(self, cmd: str, *args: Any, **kwargs: Any) -> Any:
        req = Request(
            self._url(),
            data=json.dumps({'cmd': cmd, 'args': list(args), 'kwargs': kwargs}).encode(),
            headers={'Content-type': 'application/json'},
        )
        res = json.loads(urlopen(req, timeout=self.timeout_secs).read())
        if 'value' in res:
            return res['value']
        elif 'error' in res:
            raise ValueError(f'pf: Error. {res["error"]}')
        else:
            raise ValueError(f'pf: Communication error. {res}')

    def statejson(self) -> dict[str, Any] | None:
        return self._call('statejson')

    def set_speed(self, value: int):
        if not (0 < value <= 100):
            raise ValueError(f'Speed out of range: {value=}')
        return self._call('set_speed', value)

    def _translate_cmd(self, cmd: str) -> list[str]:
        cmd = cmd.strip()
        if not cmd:
            return []

        parts = cmd.split()
        name = parts[0].lower()
        if name == 'movec' and len(parts) >= 8:
            return [' '.join(['MoveC_WithoutRail', *parts[1:6]])]
        elif name == 'movec_rel' and len(parts) >= 8:
            return [' '.join(['MoveC_Rel_WithoutRail', *parts[1:6]])]
        elif name == 'wherejson':
            return ['statejson']
        else:
            return [cmd]

    def _commands_from_move(self, move: Move) -> list[str]:
        commands: list[str] = []
        for line in move.to_pf_script().splitlines():
            for cmd in line.split(';'):
                commands += self._translate_cmd(cmd)
        return commands

    def execute_moves(self, ms: list[Move]):
        cmds: list[str] = []
        for move in ms:
            cmds += self._commands_from_move(move)
        if cmds:
            return self._call('run_cmds', cmds)

    def init(self):
        self._call('hp', '1')
        self._call('attach')
        self._call('home')
