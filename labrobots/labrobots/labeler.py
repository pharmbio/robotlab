from __future__ import annotations
from dataclasses import *
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import *

import threading
import time
import json
import functools

from .machine import Machine, Log

P = ParamSpec('P')
R = TypeVar('R')

@dataclass(frozen=True)
class Labeler(Machine):
    args: List[str] = field(default_factory=list)
    input_queue: 'Queue[Tuple[str, Log, Queue[Any]]]' = field(default_factory=Queue)

    def init(self):
        threading.Thread(target=self._handler, daemon=True).start()

    def _send(self, cmd: str, *args: str) -> dict[str, Any]:
        with self.exclusive():
            reply_queue: Queue[Any] = Queue()
            msg = ' '.join([
                part.replace(' ', '\\s').replace('\n', '\\s').encode('ascii', errors='replace').decode()
                for part in [cmd, *args]
            ])
            self.input_queue.put((msg, self.log, reply_queue))
            return reply_queue.get()

    def _handler(self):
        with Popen(
            self.args,
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            bufsize=1,  # line buffered
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
        ) as p:
            stdin = p.stdin
            stdout = p.stdout
            assert stdin
            assert stdout

            def read_until_ready(t0: float, log: Log) -> List[Dict[str, Any]]:
                lines: List[Dict[str, Any]] = []
                while True:
                    exc = p.poll()
                    if exc is not None:
                        t = round(time.monotonic() - t0, 3)
                        log(t, 'labeler', f"exit code: {exc}")
                        lines += [{'error': 'exit', 'exit_code': exc}]
                        return lines
                    line = stdout.readline().rstrip()
                    t = round(time.monotonic() - t0, 3)
                    short_line = line
                    if len(short_line) > 250:
                        short_line = short_line[:250] + '... (truncated)'
                    log(t, 'labeler', short_line)
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        data = {'error': 'JSONDecodeError', 'details': str(e), 'line': line}
                    except Exception as e:
                        data = {'error': str(type(e)), 'details': str(e), 'line': line}
                        return lines
                    log(t, 'labeler', **data)
                    if data.get('status') == 'ready':
                        return lines
                    else:
                        lines += [data]

            lines = read_until_ready(time.monotonic(), Machine.default_log)
            while True:
                msg, log, reply_queue = self.input_queue.get()
                t0 = time.monotonic()
                stdin.write(msg + '\n')
                stdin.flush()
                lines = read_until_ready(t0, log)
                success = not any(data.get('error') for data in lines)
                response = dict(**lines[-1], lines=lines, success=success)
                reply_queue.put_nowait(response)

    @staticmethod
    def _rpc(fn: Callable[Concatenate['Labeler', P], R]) -> Callable[Concatenate['Labeler', P], R]:
        @functools.wraps(fn)
        def inner(self: Labeler, *args: P.args, **kwargs: P.kwargs) -> R:
            if kwargs:
                raise ValueError(f'Must use positional arguments, not {kwargs=}')
            res = self._send(fn.__name__, *map(str, args))
            err = res.get('error')
            if err:
                raise ValueError(err)
            else:
                return res.get('value') # type: ignore
        return inner

    @_rpc
    def abort(self) -> int: ...

    @_rpc
    def exit(self) -> NoReturn: ...

    @_rpc
    def initialize(self, labeler: str="labeler") -> int: ...

    @_rpc
    def print_label(
        self, format_index: int,
        field0: str="", field1: str="", field2: str="",
        field3: str="", field4: str="", field5: str=""
    ) -> int: ...

    @_rpc
    def print_and_apply(
        self, format_index: int, sides: int, drop_stage: bool,
        field0: str="", field1: str="", field2: str="",
        field3: str="", field4: str="", field5: str=""
    ) -> int: ...

    @_rpc
    def print_by_format(
        self, format_name: str,
        field0: str="", field1: str="", field2: str="",
        field3: str="", field4: str="", field5: str=""
    ) -> int: ...

    @_rpc
    def print_and_apply_by_format(
        self, format_name: str, sides: int, drop_stage: bool,
        field0: str="", field1: str="", field2: str="",
        field3: str="", field4: str="", field5: str=""
    ) -> int: ...

    @_rpc
    def read_barcode(self, sides: int) -> str: ...

    @_rpc
    def get_version(self) -> str: ...

    @_rpc
    def get_firmware(self) -> str: ...

    @_rpc
    def home_stage(self) -> int: ...

    @_rpc
    def drop_stage(self, drop: bool) -> int: ...

    @_rpc
    def rotate_stage(self, angle: float) -> int: ...

    @_rpc
    def rotate_180(self) -> int: ...

    @_rpc
    def get_remaining_labels(self) -> int: ...

    @_rpc
    def enumerate_formats(self) -> str: ...

    @_rpc
    def show_diags_dialog(self) -> None: ...

    @_rpc
    def enumerate_profiles(self) -> str: ...

