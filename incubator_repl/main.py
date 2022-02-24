import socket
import traceback
import re
from dataclasses import dataclass
from typing import Union, Tuple, Dict

SLOTS = {char: i+1 for i, char in enumerate("LRDEFGIJKMNO")}

@dataclass(frozen=True)
class STX:
    id="STX"
    host="localhost"
    port=3333

    def loop(self):
        while True:
            print("ready")
            line = input()
            print("line", repr(line))
            line = line.replace('\\', ' ').strip()
            print("line", repr(line))
            command, *args = re.split(r'[\s]+', line)
            print("command", repr([command, *args]))
            try:
                if hasattr(self, command):
                    getattr(self, command)(*args)
                else:
                    response = self.call(command, *args)
                    assert response != "E1"
                print("success")
            except Exception as e:
                print("error", str(e))
                traceback.print_exc()

    def parse_pos(self, pos: str) -> Tuple[int, int]:
        slot = SLOTS.get(pos[0])
        if not slot:
            raise ValueError("pos should start with L or R indicate cassette 1 or 2")
        # pos[1:] should be level, 1-indexed
        level = int(pos[1:])
        return slot, level

    def parse_climate(self, response: str) -> Dict[str, float]:
        """
        temp:  target temperature in °C.
        humid: target relative humidity in percent.
        co2:   target CO₂ concentration in percent.
        n2:    target N₂ concentration in percent.
        """
        temp, humid, co2, n2 = map(float, response.split(";"))
        climate = {
            "temp": temp,
            "humid": humid,
            "co2": co2,
            "n2": n2,
        }
        print("value", climate)
        return climate

    def reset_and_activate(self):
        self.call("STX2Reset")
        response = self.call("STX2Activate")
        assert response == "1" or response == "1;1"

    def get_status(self):
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
        print("value", value)

    def get_climate(self):
        response = self.call("STX2ReadActualClimate")
        return self.parse_climate(response)

    def get_target_climate(self):
        response = self.call("STX2ReadSetClimate")
        return self.parse_climate(response)

    def set_target_climate(self, temp, humid, co2, n2):
        # I think the STX driver wants co2 and n2 in the opposite order here...
        self.call("STX2WriteSetClimate", temp, humid, co2, n2)

    def get(self, pos: str):
        slot, level = self.parse_pos(pos)
        self.move(src_pos='Hotel', src_slot=slot, src_level=level)

    def put(self, pos: str):
        slot, level = self.parse_pos(pos)
        self.move(trg_pos='Hotel', trg_slot=slot, trg_level=level)

    def move(
        self,
        src_pos:   str = 'TransferStation',
        src_slot:  int = 0,
        src_level: int = 0,
        trg_pos:   str = 'TransferStation',
        trg_slot:  int = 0,
        trg_level: int = 0,
    ):
        # SrcID,        TrgId:    device identifier
        # SrcPos,       TrgPos:   1=TransferStation, 2=Slot-Level Position
        # SrcSlot,      TrgSlot:  plate slot (cassette) position
        # SrcLevel,     TrgLevel: plate level position
        # TransSrcSlot, TransTrgSlot: (not relevant for us)
        # SrcPlType,    TrgPlType: plate type 0=MTP, 1=DWP, 3=P28 (not sure if matters)
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

    def call(self, command_name: str, *args: Union[str, float, int]):
        args = (self.id, *args)
        csv_args = ",".join(str(arg) for arg in args)
        return self.send(f'{command_name}({csv_args})')

    def send(self, cmd: str) -> str:
        RECEIVE_BUFFER_SIZE = 8192 # Also max response length since we are not looping response if buffer gets full

        cmd_as_bytes = (cmd + '\r').encode("ascii")

        # send and recieve
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, self.port))
        s.sendall(cmd_as_bytes)
        print("sent", cmd_as_bytes)
        received = s.recv(RECEIVE_BUFFER_SIZE)
        print("received", repr(received))
        s.close()

        # decode recieved byte array to ascii
        response = received.decode('ascii')
        response = response.strip()

        print("response", response)

        return response

def main():
    print('Using SLOTS:', SLOTS)
    STX().loop()

if __name__ == '__main__':
    main()

