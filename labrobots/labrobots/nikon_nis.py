from __future__ import annotations
from dataclasses import *
from typing import *

import time
import textwrap
import string

from subprocess import Popen

from .machine import Machine, Cell

from hashlib import sha256
from pathlib import Path

import threading
from threading import RLock

class Status(TypedDict):
    running: bool
    returncode: None | int

@dataclass(frozen=True)
class NikonNIS(Machine):
    '''
    Communication with the Nikon NIS Elements software, by calling the gui exe with a macro argument.
    '''
    nis_exe_path: str = r'C:\Program Files\NIS-Elements\nis_ar.exe'
    current_process: Cell[Popen[bytes] | None] = field(default_factory=lambda: Cell(None))
    lock: RLock = field(default_factory=RLock, repr=False)

    def run_macro(self, macro: str, name_prefix: str='macro'):
        '''
        Call a macro, given as a string, and wait for it to complete (in the background).

        Use status or is_running to see if it completed.
        '''
        with self.lock:
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
            self.current_process.value = None
            def start_process():
                # -mw: run macro and wait for completion
                # I had to use a thread or else the Windows subprocess sometimes blocked the main process
                p = Popen([self.nis_exe_path, '-mw', str(macro_path.resolve())])
                self.current_process.value = p
            t = threading.Thread(target=start_process)
            t.start()
            while self.current_process.value is None:
                time.sleep(0.1)

    def StgMoveZ(self, z_um: float | int):
        '''Absolute move of stage in Z direction. Unit: micrometers, range: [0, 10000]'''
        return self.run_macro(f'StgMoveZ({z_um},0)', 'StgMoveZ')

    def StgMoveXY(self, x_um: float | int, y_um: float | int):
        '''Absolute move of stage in XY direction. Unit: micrometers, range x: [-57000, 57000], range y: [-37500, 37500]'''
        return self.run_macro(f'StgMoveXY({x_um},{y_um},0)', 'StgMoveXY')

    def StgMoveToA01(self):
        '''Move to about the center of the A01 well. This is the neutral position for the robotarm.'''
        return self.StgMoveXY(51884, -34132)

    def InitLaser(self, duration_secs: int = 30):
        '''Initialize the laser to avoid bleaching in the ramp-up phase. Default duration: 30s'''
        return self.run_macro(f'''
            Live();
            Wait({duration_secs});
            Freeze();
        ''', 'InitLaser')

    def CloseAllDocuments(self):
        '''Close all documents without saving'''
        return self.run_macro('CloseAllDocuments(QUERYSAVE_NO)', 'CloseAllDocuments')

    def RunJob(self, job_name: str, project: str, plate: str):
        '''Run a job by name, saving it to a directory based on the project and plate.'''
        ok = string.ascii_letters + string.digits + '_-'
        for s, ok_for_s in {job_name: ok + ' ', project: ok, plate: ok}.items():
            for c in s:
                if c not in ok_for_s:
                    raise ValueError(f'Input {s!r} contains illegal character {c!r}')
            if not s:
                raise ValueError(f'Input {s!r} is empty')
            if not s[0].isalpha():
                raise ValueError(f'Input {s!r} does not start with alpha')
            if s.strip() != s:
                raise ValueError(f'Input {s!r} contains trailing whitespace')
        assert len(project + plate) < 900
        macro: str = f'''
            int64 job_key;
            char json[1000] = "{{'StoreToFsOnly.Folder':'Z:/{project}/{plate}/'}}";
            StrExchangeChar(json, 34, 39); //Exchange single to double quotes - ASCII codes: 34 = ["], 39 = [']
            Jobs_GetJobKey("Demo", "{job_name}", &job_key, NULL, 0);
            Jobs_RunJobInitParam(job_key, json);
        '''
        prefix = f'run-job-{job_name}-{project}-{plate}'
        prefix = prefix.replace('-', '_')
        prefix = prefix.replace(' ', '_')
        return self.run_macro(macro, prefix)

    def status(self) -> Status:
        with self.lock:
            p = self.current_process.value
            if p is None:
                return {'running': False, 'returncode': None}
            else:
                returncode = p.poll()
                return {'running': returncode is None, 'returncode': returncode}

    def is_running(self) -> bool:
        return self.status()['running']

    def kill(self):
        with self.lock:
            p = self.current_process.value
            if p:
                p.kill()
            time.sleep(1.0)
            return self.status()

    def screen_scraper_status(self) -> dict[str, str]:
        import contextlib
        import sqlite3
        import json
        with contextlib.closing(sqlite3.connect('ocr.db', isolation_level=None)) as c:
            data = c.execute('select t, data from ocr order by t desc limit 1').fetchone()
            return json.loads(data)

