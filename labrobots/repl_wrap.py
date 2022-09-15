from dataclasses import dataclass, field
from queue import Queue
from subprocess import Popen, PIPE, STDOUT
from typing import Any, List, Tuple

import ast
import threading
import time

from .machine import Machine

@dataclass
class ReplWrap(Machine):
    name: str
    args: List[str]
    input_queue: 'Queue[Tuple[str, Queue[Any]]]' = field(default_factory=Queue)
    is_ready: bool = False

    def __post_init__(self):
        threading.Thread(target=self._handler, daemon=True).start()

    def message(self, cmd: str, arg: str=""):
        if self.is_ready:
            reply_queue: Queue[Any] = Queue()
            if arg:
                msg = cmd + ' ' + arg
            else:
                msg = cmd
            self.input_queue.put((msg, reply_queue))
            return reply_queue.get()
        else:
            return dict(success=False, lines=["not ready"])

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

            def read_until_ready(t0: float):
                lines: List[str] = []
                value: None = None
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
                        return lines, value
                    value_line = False
                    if line.startswith('value'):
                        try:
                            value = ast.literal_eval(line[len('value '):])
                            value_line = True
                        except:
                            pass
                    if not value_line:
                        lines += [line]

            lines = read_until_ready(time.monotonic())
            while True:
                self.is_ready = True
                msg, reply_queue = self.input_queue.get()
                self.is_ready = False
                t0 = time.monotonic()
                stdin.write(msg + '\n')
                stdin.flush()
                lines, value = read_until_ready(t0)
                success = any(line.startswith('success') for line in lines)
                response = dict(lines=lines, success=success)
                if value is not None:
                    response['value'] = value
                reply_queue.put_nowait(response)
