from __future__ import annotations
from dataclasses import *
from typing import *

from .machine import Machine

import atexit
import time

import RPi.GPIO as GPIO

GPIO: Any = GPIO # quiet pyright

@dataclass(frozen=True)
class NikonStage(Machine):
    def init(self):
        atexit.register(GPIO.cleanup)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(2, GPIO.OUT)
        GPIO.setup(3, GPIO.IN)
        GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def close(self):
        GPIO.output(2, GPIO.LOW)

    def open(self):
        GPIO.output(2, GPIO.HIGH)

    def status(self):
        return dict(
            busy = bool(not GPIO.input(3)),
            plate = bool(GPIO.input(4)),
        )

    def print_status(self):
        for _ in range(10):
            self.log(self.status())
            time.sleep(0.5)
