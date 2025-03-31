from typing import *
from serial import Serial # type: ignore
from .machine import Machine
from dataclasses import *
import contextlib
import time

# from ExternalControlProtocolRevC.pdf
ErrorCodes = {
    '-1': 'A user-defined error code, stored in the HTSError variable from a journal',
    '0':  'Error code Not Defined',
    '1':  'MX is in Offline mode, command cannot be completed',
    '2':  'MX is in Online mode, command cannot be completed',
    '3':  'MX is in Running mode, command cannot be completed',
    '4':  'MX is in Paused mode, command cannot be completed',
    '5':  'MX is busy, command cannot be completed',
    '6':  'Timeout error occurred waiting for response from MX',
    '7':  'Error occurred moving to desired stage position',
    '8':  'Protocol file is invalid',
    '9':  'Invalid parameter specified',
    '10': 'Unexpected Command (sent to MX from the CPF)',
    '11': 'Error running a journal (if a journal fails to run properly)',
    '12': 'Error connecting to the Database',
    '13': 'Append Time Point plate validation failed (MetaXpress version 6.5 and above)',
    '14': 'Initial Plate Find Sample failed (MetaXpress version 6.5 and above)',
    '15': 'Water Immersion Source Bottle is Empty (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '16': 'Water Immersion Waste Bottle is Full (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '17': 'Water Immersion System Leak Detected (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '18': 'Water Immersion Pressure Test Failed (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '19': 'Water Immersion Vacuum Test Failed (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '20': 'Water Immersion Timeout with WI module (MetaXpress version 6.6 and above, for systems with Water Immersion option)',
    '21': 'Camera Timeout (MetaXpress version 6.5.5 and above)',
    '22': 'User Canceled Acquisition (MetaXpress version 6.6 and above)',
    '23': 'Failed to Find A01 Centerpoint for Round Bottom Plates (MetaXpress version 6.6 and above)',
}

@dataclass
class ConnectedIMX:
    com: Any # Serial
    log: Callable[..., None] = field(default_factory=lambda: Machine.default_log)

    def write(self, line: str):
        msg = line.strip().encode('ascii')
        assert b'\n' not in msg
        assert b'\r' not in msg
        msg = msg + b'\r\n'
        self.log(f'imx.write({msg!r})')
        self.com.write(msg)

    def read(self) -> str:
        reply_bytes: bytes = self.com.readline()
        self.log(f'imx.read() = {reply_bytes!r}')
        reply = reply_bytes.decode('ascii').strip()
        return reply

    def send(self, line: str) -> list[str]:
        self.write(line)
        return self.read().split(',')[1:]

@dataclass(frozen=True)
class IMX(Machine):
    com_port: str = 'COM4'

    @contextlib.contextmanager
    def _connect(self):
        with self.exclusive():
            com = Serial(self.com_port, timeout=5)
            yield ConnectedIMX(com, log=self.log)
            com.close()

    def send_raw(self, line: str) -> list[str]:
        with self._connect() as con:
            return con.send(line)

    def send(self, cmd: str, *args: str) -> list[str]:
        return self.send_raw(','.join(['1', cmd, *args]))

    def online(self):
        return self.send('ONLINE')

    def status(self):
        return self.send('STATUS')

    def goto(self, pos: str):
        self.send('GOTO', pos)
        # we wait for READY,LOAD or READY,SAMPLE but it might be enough to just wait for OK
        while True:
            if self.status()[:2] == ['READY', pos]:
                break
            time.sleep(0.5)

    def goto_loading(self):
        return self.goto('LOAD')

    def leave_loading(self, pos: str):
        return self.goto('SAMPLE')

    def acquire(self, hts_file: str):
        r'''
        Full path to hts_file like z:\cpf\jenny.hts

        Status will be things like:
            ['RUNNING', '',   ['0', '0', '0']]
            ['RUNNING', '',   ['B', '2', '0']]
            ['DONE',    '',   ['F', '7', '0']]
            ['ERROR',   '14', []]

        First reply should be OK
        '''
        return self.send('RUN', '', hts_file)
