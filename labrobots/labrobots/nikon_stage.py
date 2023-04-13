from __future__ import annotations
from dataclasses import *
from typing import *

import atexit

@dataclass(frozen=True)
class NikonStage:
    def init(self):
        atexit.register(self.GPIO.cleanup)
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setup(2, self.GPIO.OUT)
        self.GPIO.setup(3, self.GPIO.IN)
        self.GPIO.setup(4, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def close(self):
        self.GPIO.output(2, self.GPIO.LOW)

    def open(self):
        self.GPIO.output(2, self.GPIO.HIGH)

    def status(self):
        return dict(
            busy = bool(not self.GPIO.input(3)),
            plate = bool(self.GPIO.input(4)),
        )

    def print_status(self):
        import time
        for _ in range(10):
            print(self.status())
            time.sleep(0.5)

    @property
    def GPIO(self) -> Any:
        import RPi.GPIO as GPIO # type: ignore
        return GPIO
