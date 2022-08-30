from __future__ import annotations
from typing import Callable, Any, TypeAlias
import signal
import atexit
import sys

Handler: TypeAlias = Callable[[int, Any], None]

_handlers: list[Handler] = []

def add_handler(h: Handler):
    _handlers.append(h)

def handle_signal(signum: int, _frame: Any):
    print('Handling signal', signum)
    for h in _handlers:
        h(signum, _frame)
    print('Done handling signal', signum)
    if signum != 0:
        sys.exit(1)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
atexit.register(lambda: handle_signal(0, None))
