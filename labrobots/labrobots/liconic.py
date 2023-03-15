from __future__ import annotations
import socket
from dataclasses import *
from typing import *

from .machine import Machine

@dataclass(frozen=True)
class STX(Machine):
    id="STX"
    host="localhost"
    port=3333

    def call(self, command_name: str, *args: Union[str, float, int]):
        '''
        Call any STX command.

        Example: curl -s 10.10.0.56:5050/incu/call/STX2ReadActualClimate
        '''
        args = (self.id, *args)
        csv_args = ",".join(str(arg) for arg in args)
        return self._send(f'{command_name}({csv_args})')

    def _send(self, cmd: str) -> str:
        with self.atomic():
            RECEIVE_BUFFER_SIZE = 8192 # Also max response length since we are not looping response if buffer gets full

            cmd_as_bytes = (cmd + '\r').encode("ascii")

            # send and recieve
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host, self.port))
            s.sendall(cmd_as_bytes)
            self.log("sent", cmd_as_bytes)
            received = s.recv(RECEIVE_BUFFER_SIZE)
            self.log("received", repr(received))
            s.close()

            # decode recieved byte array to ascii
            response = received.decode('ascii')
            response = response.strip()

            self.log("response", response)

            return response

    def _parse_pos(self, pos: str) -> Tuple[int, int]:
        if pos[0] == "L":
            slot = 1
        elif pos[0] == "R":
            slot = 2
        else:
            casette_str, x, level_str = pos.partition('x')
            if x != 'x':
                raise ValueError("pos should start with L or R indicate cassette 1 or 2, or <CASETTE>x<LEVEL>")
            slot = int(casette_str)
            level = int(level_str)
            return slot, level
        # pos[1:] should be level, 1-indexed
        level = int(pos[1:])
        return slot, level

    def _parse_climate(self, response: str) -> Dict[str, float]:
        '''
        temp:  temperature in °C.
        humid: relative humidity in percent.
        co2:   CO₂ concentration in percent.
        n2:    N₂ concentration in percent.
        '''
        temp, humid, co2, n2 = map(float, response.split(";"))
        climate = {
            "temp": temp,
            "humid": humid,
            "co2": co2,
            "n2": n2,
        }
        return climate

    def get_status(self) -> dict[str, bool]:
        response = self.call("STX2GetSysStatus")
        response = int(response)
        assert response != -1
        bits = {
            'System Ready':          0,
            'Plate Ready':           1,
            'System Initialized':    2,
            'XferStn status change': 3,
            'Gate closed':           4,
            'User door':             5,
            'Warning':               6,
            'Error':                 7,
        }
        value = {
            name: bool(response & (1 << bit))
            for name, bit in bits.items()
        }
        return value

    def get_climate(self):
        '''
        temp:  current temperature in °C.
        humid: current relative humidity in percent.
        co2:   current CO2 concentration in percent.
        n2:    current N2 concentration in percent.
        '''
        response = self.call("STX2ReadActualClimate")
        return self._parse_climate(response)

    def get_target_climate(self) -> dict[str, float]:
        '''
        temp:  target temperature in °C.
        humid: target relative humidity in percent.
        co2:   target CO2 concentration in percent.
        n2:    target N2 concentration in percent.
        '''
        response = self.call("STX2ReadSetClimate")
        return self._parse_climate(response)

    def set_target_climate(self, temp: str, humid: str, co2: str, n2: str):
        '''
        temp:  target temperature in °C.
        humid: target relative humidity in percent.
        co2:   target CO2 concentration in percent.
        n2:    target N2 concentration in percent.

        Maybe driver wants co2 and n2 in the opposite order here...
        '''
        self.call("STX2WriteSetClimate", temp, humid, co2, n2)

    def reset_and_activate(self):
        self.call("STX2Reset")
        response = self.call("STX2Activate")
        assert response == "1" or response == "1;1"

    def get(self, pos: str):
        """
        Gets the plate from a position, L<LEVEL> or R<LEVEL> indicate cassette 1 or 2, or <CASETTE>x<LEVEL>.
        """
        slot, level = self._parse_pos(pos)
        self._move(src_pos='Hotel', src_slot=slot, src_level=level)

    def put(self, pos: str):
        """
        Puts the plate to a position, L<LEVEL> or R<LEVEL> indicate cassette 1 or 2, or <CASETTE>x<LEVEL>.
        """
        slot, level = self._parse_pos(pos)
        self._move(trg_pos='Hotel', trg_slot=slot, trg_level=level)

    def _move(
        self,
        src_pos:   str = 'TransferStation',
        src_slot:  int = 0,
        src_level: int = 0,
        trg_pos:   str = 'TransferStation',
        trg_slot:  int = 0,
        trg_level: int = 0,
    ):
        '''
        SrcID,        TrgId:    device identifier
        SrcPos,       TrgPos:   1=TransferStation, 2=Slot-Level Position
        SrcSlot,      TrgSlot:  plate slot (cassette) position
        SrcLevel,     TrgLevel: plate level position
        TransSrcSlot, TransTrgSlot: (not relevant for us)
        SrcPlType,    TrgPlType: plate type 0=MTP, 1=DWP, 3=P28 (not sure if matters)
        '''
        args = {
            # SrcID: self.id (implicit, added by call),
            'SrcPos':       1 if src_pos == 'TransferStation' else 2,
            'SrcSlot':      src_slot,
            'SrcLevel':     src_level,
            'TransSrcSlot': 1,
            'SrcPlType':    1,
            'TrgID':        self.id,
            'TrgPos':       1 if trg_pos == 'TransferStation' else 2,
            'TrgSlot':      trg_slot,
            'TrgLevel':     trg_level,
            'TransTrgSlot': 1,
            'TrgPlType':    1,
        }
        assert self.call('STX2ServiceMovePlate', *args.values()) == "1"

