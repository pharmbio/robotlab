from __future__ import annotations
from dataclasses import *
from queue import Queue
import queue
from subprocess import Popen, PIPE, STDOUT
from typing import *
from threading import Lock

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
    input_queue: 'Queue[str]' = field(default_factory=Queue)

    event_listeners_lock: Lock = field(default_factory=Lock)
    event_listeners: 'list[Queue[str]]' = field(default_factory=list)

    stdout_forward: 'Queue[dict[str, Any]]' = field(default_factory=Queue)
    process_dead_error: dict[str, Any] = field(default_factory=dict)

    def init(self):
        threading.Thread(target=self._handler, daemon=True).start()

    def _send(self, cmd: str, *args: str) -> dict[str, Any]:
        with self.exclusive():
            msg = ' '.join([
                part.replace(' ', '\\s').replace('\n', '\\s').encode('ascii', errors='replace').decode()
                for part in [cmd, *args]
            ])
            self.input_queue.put(msg)
            lines: list[dict[str, Any]] = []
            while True:
                if self.process_dead_error:
                    return dict(self.process_dead_error)
                data = self.stdout_forward.get()
                self.log(repr(data), **data)
                if data.get('status') == 'ready' and len(lines) > 1:
                    return dict(**lines[-1], lines=lines)
                lines += [data]

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

            log = Log.make('labeler')

            def writer():
                while True:
                    msg = self.input_queue.get()
                    if self.process_dead_error:
                        return
                    log(f'repl.write({msg!r})', msg=msg)
                    stdin.write(msg + '\n')
                    stdin.flush()

            threading.Thread(target=writer, daemon=True).start()

            while True:
                exc = p.poll()
                if exc is not None:
                    log(f'exit code: {exc}')
                    self.process_dead_error.update({'error': 'exit', 'exit_code': exc})
                    self.stdout_forward.put_nowait(self.process_dead_error)
                    return

                line = stdout.readline().rstrip()
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    data = {'error': 'JSONDecodeError', 'details': str(e), 'line': line}
                except Exception as e:
                    data = {'error': str(type(e)), 'details': str(e), 'line': line}
                log(f'repl.read().as_json() = {data!r}', line=line, **data)
                if (event := data.get('event')):
                    with self.event_listeners_lock:
                        listeners = [*self.event_listeners]
                        self.event_listeners.clear()
                    for listener in listeners:
                        log(f'Notifying listener {listener} of event {event!r}')
                        listener.put_nowait(event)
                else:
                    self.stdout_forward.put_nowait(data)


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

    def wait_for_green_button(self) -> Literal['green_button', 'timeout', 'error']:
        listener = Queue[str]()
        self.log('Registering for event listener')
        with self.event_listeners_lock:
            self.event_listeners.append(listener)
        try:
            self.log('Listening for event')
            event = listener.get(timeout=30.0)
            self.log(f'Received event {event!r}')
            if event == 'green_button':
                return event
            else:
                return 'error'
        except queue.Empty:
            return 'timeout'

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

