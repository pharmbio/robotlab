from typing import Any
import os
from serial import Serial # type: ignore
from .machine import Machine

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


class IMX(Machine):
    def init(self):
        COM_PORT = os.environ.get('IMX_COM_PORT', 'COM4')
        print('imx: Using IMX_COM_PORT', COM_PORT)
        self.imx: Any = Serial(COM_PORT, timeout=5)

    def _send(self, cmd: str, *args: str):
        msg_str = ','.join([cmd, *args])
        msg = msg_str.strip().encode()
        assert b'\n' not in msg
        assert b'\r' not in msg
        msg = msg + b'\r\n'
        n = self.imx.write(msg)
        print('message sent', n, 'bytes:', repr(msg))
        reply_bytes: bytes = self.imx.readline()
        print('message reply', repr(reply_bytes))
        reply = reply_bytes.decode().strip()
        parts = reply.split(',')
        if len(parts) < 2:
            print('error')
            print('message too few parts')
        elif parts[1] == 'ERROR':
            print('error')
            if len(parts) >= 4:
                _machine_id, _error, arg, code, *_ = parts
                err = ErrorCodes.get(code)
                print('message arg', arg)
                print('message error', err)
                return err
        else:
            print('success')
            return reply

    def online(self):
        return self._send('ONLINE')

    def status(self):
        return self._send('STATUS')

    def goto(self, pos: str):
        return self._send('GOTO', pos.upper())

    def run(self, plate_id: str, hts_file: str):
        return self._send('RUN', plate_id, hts_file)

