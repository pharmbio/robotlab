from __future__ import annotations
from typing import Callable, Any, TypeAlias
import signal
import atexit
import sys

Handler: TypeAlias = Callable[[int, Any], int | None]

_handlers: list[Handler] = []

def add_handler(h: Handler):
    _handlers.append(h)

def handle_signal(signum: int, _frame: Any):
    print('Handling signal', signum)
    exc: int | None = None
    for h in _handlers:
        print('Running handler', h)
        e = h(signum, _frame)
        if e is not None:
            exc = e
    if signum in (signal.SIGTERM, signal.SIGINT):
        exc = 1
    print('result', signum, exc)
    if exc is not None:
        sys.exit(exc)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
atexit.register(lambda: handle_signal(0, None))
