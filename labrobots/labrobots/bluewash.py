from typing import *
from serial import Serial # type: ignore
from .machine import Machine
from dataclasses import *
from pathlib import Path
import contextlib
import time
import textwrap
import re

def timeit(desc: str=''):
    # The inferred type for the decorated function is wrong hence this wrapper to get the correct type

    @contextlib.contextmanager
    def worker():
        t0 = time.monotonic_ns()
        yield
        T = time.monotonic_ns() - t0
        print(f'{T/1e6:.1f}ms {desc}')

    return worker()

NoReply = -1
HTI_NoError = 0
HTI_ProgEnd = 21
HTI_ERR_FILE_NOT_FOUND = 16
Errors = {
    -1: "No reply from BlueWash",
     0: "HTI_NoError Successful command execution Note: for integrated solutions, wait for Err=00 before sending next command",
     1: "HTI_ERR_RASPICOMM_ALREADY_ INITIALIZED Already Initialized - raspicomm_Init() already called",
     2: "HTI_ERR_RASPICOMM_INIT",
     3: "HTI_ERR_STEPROCKER_INIT",
     4: "HTI_ERR_EPOS_READ_PARAMETER",
     5: "HTI_ERR_EPOS_COMMAND",
     6: "HTI_ERR_STEPROCKERStepRockerResult != SUCCESS",
     7: "HTI_ERR_GETPROGSscandir resulted in error",
     8: "Not used",
     9: "HTI_ERR_DCMOT_NOT_INITIALIZED",
    10: "Not used",
    11: "HTI_ERR_INVALID_PARAM Function called with an invalid parameter",
    12: "HTI_ERR_WIRINGPI_SETUP Error at wiringPiSetup",
    13: "HTI_ERR_WIRINGPI_ISR Error at wiringPiISR, Unable to setup Input isr",
    14: "HTI_ERR_EPOS_INIT openEPOS() failure",
    15: "HTI_ERR_UNKNOWN_CMD Unknown command received. Typo or transmission error. Check spelling, send command with “$” prefix to avoid transmission errors. steprocker_Init() failure Error Card not enabled, send dcmotenable before use Does not interrupt execution of program",
    16: "HTI_ERR_FILE_NOT_FOUND",
    17: "HTI_ERR_SYNTAX_IN_PROGRAM",
    18: "HTI_ERR_STEPROCKER_HOMING - SENSOR",
    19: "HTI_ERR_WIRINGPI_I2C_SETUP",
    20: "HTI_ERR_WIRINGPI_I2C_READ",
    21: "HTI_ProgEnd Successful prog or servprog execution Note: for integrated solutions, wait for Err=21 to determine prog or servprog completion",
    22: "HTI_ERR_POTENTIAL_COLLISON Can't move rotor because racksensor shows potential collision between rotor and rack or door.",
    23: "HTI_ERR_EPOS_STATE Epos is in wrong state to move (!=7) Try to call rotoron. May be caused by waste liquid backup in rotor space. Check waste drain.",
    24: "HTI_ERR_DOOR_TIMEOUT Door could did not open / close within allowed time, see Adjusting door sensors or check for object trapped in door.",
    25: "HTI_ERR_RACK_TIMEOUT Positioning sensor not reached within allowed time",
    26: "HTI_ERR_ROTOR_VIBRATIONS Vibrations during centrifugation occurred. See Calibrating vibration sensor",
    27: "HTI_ERR_CARRIER_POSITION Carrier is in wrong position or missing",
    28: "HTI_ERR_DOOR_OPENED Door must be closed before centrifugation",
    29: "HTI_ERR_DOOR_CLOSED Door must be opened before rack movement",
    30: "HTI_ERR_BUFFER Too many parameters or buffer length exceeded",
    31: "HTI_ERR_QUICKSTOP Quickstop was pressed",
    32: "HTI_ERR_ROTORSTOP Quickstop of rotor because homingsensor(s) or rack changed during centrifugation",
    33: "HTI_ERR_STEPROCKER_ANSWER_TIMEOUT No or no complete answer was received from steprocker (stepper motors)",
    34: "HTI_ERR_WIRINGPI_I2C_WRITE Write error to I2C connected devices",
    35: "HTI_ERR_WRITE_FILE Open file for write access not successful",
    36: "HTI_ERR_TURNTABLE_TIMEOUT Not applicable",
    37: "HTI_ERR_TURNTABLE_COLLISION Not applicable",
    38: "HTI_ERR_PROGRAM_IS_RUNNING Illegal command issued while other command running. Does not cause interruption of running command. Example for legal parallel command: getstatus",
    39: "HTI_ERR_DOOR_OPEN (or Copyprog on existing file? or IO error such as invalid filename?) Issued when door opens while centrifuge runs, e.g., when door is forced open, or a sensor malfunction indicates that door is open. Centrifuge enters emergency stop.",
    40: "HTI_ERR_INVALID_PARAMETER_COMBINATION From dispense: Staccato volume error; dispense volume too low for staccato mode From setpwmfrequence: wrong parameter combination, issue setpwm 1",
    41: "HTI_ERR_FILE_EXISTS From copyprog: cannot copy prog because 2- digit index already exists on Blue® Washer",
    42: "HTI_ERR_TOO_MANY_LINES From readprog, runprog or runservprog: Prog or servprog has more than 160 lines",
    43: "HTI_ERR_WRONG_CANIOANA_FIRMWARE From setpwm: Canioana Firmware Version >= Zentrifuge_ca_X1.0 required to edit PWMFREQUENCE",
    44: "HTI_ERR_TIMEOUT_ROTOR_MOVE_ENDLESS 10min timeout if rotormoveendless not followed by stopcentrifugation within 10 minutes",
    45: "HTI_ERR_CANIOANA_TIMEOUT From: rundosingpump. If LASER = 1, can also be sent from laserteachpositions and rackhome. No complete answer from Canioana board was received within allowed time",
}

@dataclass
class ConnectedBlueWash:
    com: Any # Serial

    def write(self, line: str):
        msg = line.strip().encode() + b'\r\n'
        print(f'bluewash.write({msg!r})')
        self.com.write(msg)

    def read(self) -> str:
        reply_bytes: bytes = self.com.readline()
        print(f'bluewash.read() = {reply_bytes!r}')
        reply = reply_bytes.decode().strip()
        return reply

    def read_until_code(self) -> Tuple[int, List[str]]:
        out: list[str] = []
        while True:
            reply = self.read()
            if reply:
                out += [reply]
            if reply.startswith('Err='):
                return int(reply[len('Err='):]), out

    def read_until_prog_end(self) -> List[str]:
        # Err=00 is OK, read until Err=21
        out: list[str] = []
        while True:
            code, reply = self.read_until_code()
            out += reply
            self.check_code(code, HTI_NoError, HTI_ProgEnd)
            if code == HTI_ProgEnd:
                return out

    def get_progs(self) -> Tuple[Set[int], List[str]]:
        self.write(f'$getprogs')
        code, lines = self.read_until_code()
        self.check_code(code, HTI_NoError)
        res = {
            int(line.split()[0])
            for line in lines
            if line and line[0].isdigit()
        }
        return res, lines

    def delete_prog(self, index: int) -> List[str]:
        progs, lines = self.get_progs()
        if index in progs:
            self.write(f'$deleteprog {index:02}')
            code, deleteprog_lines = self.read_until_code()
            self.check_code(code, HTI_NoError, HTI_ERR_FILE_NOT_FOUND)
            return lines + deleteprog_lines
        else:
            return lines

    def write_prog(self, program_code: str, index: int, program_name: str=''):
        delete_lines = self.delete_prog(index)
        lines = program_code.splitlines(keepends=False)
        self.write(f'$Copyprog {index:02} _')
        for line in lines:
            self.write('$& ' + line)
        self.write('$%')
        code, copyprog_lines = self.read_until_code()
        self.check_code(code, HTI_NoError)
        return delete_lines + copyprog_lines

    def check_code(self, code: int, *ok_codes: int) -> None:
        if code not in ok_codes:
            raise ValueError(f'Unexpected reply from BlueWash: {code=} {Errors.get(code, "unknown error")}')

@dataclass(frozen=True)
class BlueWash(Machine):
    root_dir: str
    com_port: str = 'COM6'

    @contextlib.contextmanager
    def connect(self):
        print('bluewash: Using com_port', self.com_port)
        with timeit('connection'):
            com = Serial(
                self.com_port,
                timeout=15,
                baudrate=115200
            )
            yield ConnectedBlueWash(com)
            com.close()

    def init_all(self):
        '''
        Required to run before using BlueWasher:
        Initializes linear drive, rotor, inputs, outputs, motors, valves .
        Presents working carrier (= top side of rotor) to RACKOUT.
        '''
        return self.run_servprog(1)

    def get_balance_plate(self):
        '''
        Presents balance carrier (= bottom side of rotor) to RACKOUT.
        Check whether working or balance carrier present with rotorgetpos
        '''
        return self.run_servprog(2)

    def get_working_plate(self):
        '''
        Presents working carrier (= top side of rotor) to RACKOUT.
        Check whether working or balance carrier present with rotorgetpos
        '''
        return self.run_servprog(3)

    def rackgetoutsensor(self):
        '''
        Returns “1” if rack is in RACKOUT position (plate pick- up/ drop-off), else “0”.
        If BlueWasher has not been initialized prior to issuing  this command, BlueWasher will respond with Err=33.
        This can be used to confirm BlueWasher has been initialized prior to running a method. If Err=33 received, run initialization routine $runservprog 01, see init_all()

        Note: Confirm carrier presence in RACKOUT position prior to automated plate drop-off/pick-up.
        '''
        return self.run_cmd('$rackgetoutsensor')

    def run_cmd(self, cmd: str) -> List[str]:
        with self.connect() as con:
            con.write(cmd)
            code, lines = con.read_until_code()
            con.check_code(code, HTI_NoError)
            return lines

    def run_servprog(self, index: int) -> List[str]:
        with self.connect() as con:
            with timeit('runservprog'):
                con.write(f'$runservprog {index}')
                return con.read_until_prog_end()

    def run_prog(self, index: int=99) -> List[str]:
        with self.connect() as con:
            with timeit('runprog'):
                con.write(f'$runprog {index}')
                return con.read_until_prog_end()

    def write_prog(self, *filename_parts: str, index: int=99) -> List[str]:
        filename = '/'.join(filename_parts)
        with self.connect() as con:
            with timeit('copyprog'):
                path = Path(self.root_dir) / filename
                return con.write_prog(path.read_text(), index, program_name=filename)

    def write_and_run_prog(self, *filename_parts: str, index: int=99) -> List[str]:
        return [
            *self.write_prog(*filename_parts, index=index),
            *self.run_prog(index),
        ]

    def run_test_prog(self) -> List[str]:
        return self.write_and_run_prog('bluewash-protocols/MagBeadSpinWash-2X-80ul-Blue.prog')

    def get_info(self, index: int=98, program_name: str='get_info') -> List[str]:
        program: str = '''
            $getserial
            $getfirmware
            $getipadr
        '''
        program = textwrap.dedent(program).strip()
        with self.connect() as con:
            xs = con.write_prog(program, index, program_name=program_name)
        return [
            *xs,
            *self.run_prog(index),
        ]
