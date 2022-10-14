from .machine import Machine
from dataclasses import *

@dataclass
class Squid(Machine):
    def home(self) -> None:
        raise

    def load(self) -> None:
        raise

    def acquire(self, path: str) -> None:
        # settings?
        raise

    def stop_acquire(self) -> None:
        raise

    def is_ready(self) -> bool:
        raise
