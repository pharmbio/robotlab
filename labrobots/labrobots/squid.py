from .machine import Machine
from dataclasses import *
from typing import *

@dataclass(frozen=True)
class Squid(Machine):
    def goto_loading(self) -> None:
        raise

    def leave_loading(self) -> None:
        raise

    def load_config(self, file_path: str, project_override: str='', plate_override: str='') -> None:
        raise

    def acquire(self) -> bool:
        raise

    def status(self) -> dict[str, Any]:
        raise

    def list_protocols(self) -> list[str]:
        raise
