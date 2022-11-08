from __future__ import annotations
from dataclasses import *
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import *

import threading
import time

from .machine import Machine

class BiotekResult(TypedDict):
    success: bool
    lines: list[str]

@dataclass(frozen=True)
class Biotek(Machine):
    name: str
    args: List[str]
    input_queue: 'Queue[Tuple[str, Queue[Any]]]' = field(default_factory=Queue)

    def init(self):
        threading.Thread(target=self._handler, daemon=True).start()

    def TestCommunications(self):
        return self._send("TestCommunications")

    def Run(self, *protocol_file_parts: str):
        return self._send("Run", '\\'.join(protocol_file_parts))

    def RunValidated(self, *protocol_file_parts: str):
        return self._send("RunValidated", '\\'.join(protocol_file_parts))

    def Validate(self, *protocol_file_parts: str):
        return self._send("Validate", '\\'.join(protocol_file_parts))

    def _send(self, cmd: str, arg: str="") -> BiotekResult:
        reply_queue: Queue[Any] = Queue()
        if arg:
            msg = cmd + ' ' + arg
        else:
            msg = cmd
        self.input_queue.put((msg, reply_queue))
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

            def read_until_ready(t0: float) -> list[str]:
                lines: List[str] = []
                while True:
                    exc = p.poll()
                    if exc is not None:
                        t = round(time.monotonic() - t0, 3)
                        print(t, self.name, f"exit code: {exc}")
                        lines += [f"exit code: {exc}"]
                        return lines
                    line = stdout.readline().rstrip()
                    t = round(time.monotonic() - t0, 3)
                    short_line = line
                    if len(short_line) > 250:
                        short_line = short_line[:250] + '... (truncated)'
                    print(t, self.name, short_line)
                    if line.startswith('ready'):
                        return lines
                    lines += [line]

            lines = read_until_ready(time.monotonic())
            while True:
                msg, reply_queue = self.input_queue.get()
                t0 = time.monotonic()
                stdin.write(msg + '\n')
                stdin.flush()
                lines = read_until_ready(t0)
                success = any(line.startswith('success') for line in lines)
                response = dict(lines=lines, success=success)
                reply_queue.put_nowait(response)
