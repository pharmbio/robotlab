from __future__ import annotations
from dataclasses import *
from typing import *

from .machine import Machine

import atexit
import time

import RPi.GPIO as GPIO

GPIO: Any = GPIO # make pyright quiet

class StageStatus(TypedDict):
    busy: bool
    plate: bool

@dataclass(frozen=True)
class NikonStage(Machine):
    def init(self):
        atexit.register(GPIO.cleanup)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(2, GPIO.OUT)
        GPIO.setup(3, GPIO.IN)
        GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def close(self):
        # The logic looks for transitions rather than states
        # (so the button and the command input can override each other).
        GPIO.output(2, GPIO.HIGH)
        self.delay()
        GPIO.output(2, GPIO.LOW)
        self.delay() # Ensure that the holder has time to react and set the status signal

    def open(self):
        GPIO.output(2, GPIO.LOW)
        self.delay()
        GPIO.output(2, GPIO.HIGH)
        self.delay()

    def delay(self):
        time.sleep(0.25)

    def status(self) -> StageStatus:
        return StageStatus(
            busy = bool(not GPIO.input(3)),
            plate = bool(GPIO.input(4)),
        )

    def is_busy(self) -> bool:
        return self.status()['busy']

    def has_plate(self) -> bool:
        return self.status()['plate']

    def print_status(self):
        for _ in range(10):
            self.log(self.status())
            time.sleep(0.5)
