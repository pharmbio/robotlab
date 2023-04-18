from __future__ import annotations
from dataclasses import *
from typing import *

from .machine import Machine

import atexit
import time
import textwrap

try:
    import RPi.GPIO as GPIO
except:
    GPIO: Any = None

GPIO: Any = GPIO # make pyright quiet

Green = 17
Blue = 3
Orange = 2

class StageStatus(TypedDict):
    busy: bool
    plate: bool

@dataclass(frozen=True)
class NikonStage(Machine):
    def init(self):
        atexit.register(GPIO.cleanup)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(Green, GPIO.OUT)
        GPIO.setup(Blue, GPIO.IN)
        GPIO.setup(Orange, GPIO.IN)

    def close(self):
        # The logic looks for transitions rather than states
        # (so the button and the command input can override each other).
        GPIO.output(Green, GPIO.HIGH)
        self.delay()
        GPIO.output(Green, GPIO.LOW)
        self.delay() # Ensure that the holder has time to react and set the status signal

    def open(self):
        GPIO.output(Green, GPIO.LOW)
        self.delay()
        GPIO.output(Green, GPIO.HIGH)
        self.delay()

    def delay(self):
        time.sleep(0.20)

    def status(self) -> StageStatus:
        return StageStatus(
            busy = bool(not GPIO.input(Blue)),
            plate = bool(GPIO.input(Orange)),
        )

    def is_busy(self) -> bool:
        return self.status()['busy']

    def has_plate(self) -> bool:
        return self.status()['plate']

    def print_status(self):
        for _ in range(10):
            self.log(self.status())
            time.sleep(0.5)

    def high(self):
        '''For troubleshooting: set GPIO 2 high'''
        GPIO.output(Green, GPIO.HIGH)

    def low(self):
        '''For troubleshooting: set GPIO 2 low'''
        GPIO.output(Green, GPIO.LOW)

    def pinout(self):
        '''See how the cables should be attached to the RPi pinout'''
        s = '''
                         [-]  1   2 [-]
            [GPIO 2: orange]  3   4 [-]
            [GPIO 3: blue  ]  5   6 [ground: brown ]
                         [-]  7   8 [-]
            [ ground: grey ]  9  10 [-]
            [GPIO 17: green] 11  12 [-]
                         [-] 13  14 [ground: yellow]
        '''
        s = textwrap.dedent(s).splitlines()
        return s
