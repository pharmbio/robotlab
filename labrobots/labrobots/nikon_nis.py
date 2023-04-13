from __future__ import annotations
from dataclasses import *
from typing import *

import time
import textwrap
import string

from subprocess import Popen

from .machine import Machine, Cell
from .sqlitecell import SqliteCell

from hashlib import sha256
from pathlib import Path

import threading

class Status(TypedDict):
    running: bool
    returncode: None | int

@dataclass(frozen=True)
class NikonNIS(Machine):
    nis_exe_path: str = r'C:\Program Files\NIS-Elements\nis_ar.exe'
    current_process: Cell[Popen[bytes] | None] = field(default_factory=lambda: Cell(None))

    def macro_wait(self, macro: str, name_prefix: str='macro'):
        '''
        Call a macro, given as a string, and wait for it to complete (in the background).

        Use is_running to see if it completed.
        '''
        with self.atomic():
            if self.is_running():
                raise ValueError('Already running')
            macro = textwrap.dedent(macro)
            macro = '\r\n'.join(macro.splitlines(keepends=False)) # make windows-style line-endings
            macro_bytes = macro.encode('ascii')
            macro_hash = sha256(macro_bytes).hexdigest()[:8]
            macro_dir = Path('macros')
            macro_dir.mkdir(parents=True, exist_ok=True)
            macro_path = macro_dir / f'{name_prefix}_{macro_hash}.mac'
            macro_path.write_bytes(macro_bytes)
            def start_process():
                p = Popen([self.nis_exe_path, '-mw', str(macro_path.resolve())])
                self.current_process.value = p
            t = threading.Thread(target=start_process)
            t.start()
            while self.current_process.value is None:
                time.sleep(0.1)


    def StgMoveZ(self, z_um: float | int):
        '''Absolute move of stage in Z direction. Unit: micrometers, range: [0, 10000]'''
        return self.macro_wait(f'StgMoveZ({z_um},0)', 'StgMoveZ')

    def StgMoveXY(self, x_um: float | int, y_um: float | int):
        '''Absolute move of stage in XY direction. Unit: micrometers, range x: [-57000, 57000], range y: [-37500, 37500]'''
        return self.macro_wait(f'StgMoveXY({x_um},{y_um},0)', 'StgMoveXY')

    def InitLaser(self, duration_secs: int = 30):
        '''Initialize the laser to avoid bleaching in the ramp-up phase. Default duration: 30s'''
        return self.macro_wait(f'''
            Live();
            Wait({duration_secs});
            Freeze();
        ''', 'InitLaser')

    def CloseAllDocuments(self):
        '''Close all documents without saving'''
        return self.macro_wait('CloseAllDocuments(QUERYSAVE_NO)', 'CloseAllDocuments')

    def run_job(self, job_name: str, project: str, plate: str):
        ok = string.ascii_letters + string.digits + ' _-'
        for s in (job_name, project, plate):
            for c in s:
                if c not in ok:
                    raise ValueError(f'Input {s!r} contains illegal character {c!r}')
        assert len(project + plate) < 900
        macro: str = f'''
            int64 job_key;
            char json[1000] = "{{'StoreToFsOnly.Folder':'C:/tmp/{project}/{plate}/'}}";
            StrExchangeChar(json, 34, 39); //Exchange single to double quotes - ASCII codes: 34 = ["], 39 = [']
            Jobs_GetJobKey("Demo", "{job_name}", &job_key, NULL, 0);
            Jobs_RunJobInitParam(job_key, json);
        '''
        prefix = f'run-job-{job_name}-{project}-{plate}'
        prefix = prefix.replace('-', '_')
        prefix = prefix.replace(' ', '_')
        return self.macro_wait(macro, prefix)

    def status(self) -> Status:
        p = self.current_process.value
        if p is None:
            return {'running': False, 'returncode': None}
        else:
            returncode = p.poll()
            return {'running': returncode is None, 'returncode': returncode}

    def is_running(self) -> bool:
        return self.status()['running']

    def kill(self):
        p = self.current_process.value
        if p:
            p.kill()
        time.sleep(1.0)
        return self.status()
