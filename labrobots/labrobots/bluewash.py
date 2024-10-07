from typing import *
from serial import Serial # type: ignore
from .machine import Machine
from dataclasses import *
from pathlib import Path
import contextlib
import time
import textwrap

NoReply = -1
HTI_NoError = 0
HTI_ProgEnd = 21
HTI_ERR_FILE_NOT_FOUND = 16
Errors = {
    -1: "No reply from BlueWash",
     0: "HTI_NoError Successful command execution Note: for integrated solutions, wait for Err=00 before sending next command",
     1: "HTI_ERR_RASPICOMM_ALREADY_INITIALIZED Already Initialized - raspicomm_Init() already called",
     2: "HTI_ERR_RASPICOMM_INIT",
     3: "HTI_ERR_STEPROCKER_INIT steprocker_Init() failure ",
     4: "HTI_ERR_EPOS_READ_PARAMETER",
     5: "HTI_ERR_EPOS_COMMAND",
     6: "HTI_ERR_STEPROCKER StepRockerResult != SUCCESS",
     7: "HTI_ERR_GETPROGS scandir resulted in error",
     8: "Not used",
     9: "HTI_ERR_DCMOT_NOT_INITIALIZED Error Card not enabled, send dcmotenable before use",
    10: "Not used",
    11: "HTI_ERR_INVALID_PARAM Function called with an invalid parameter",
    12: "HTI_ERR_WIRINGPI_SETUP Error at wiringPiSetup",
    13: "HTI_ERR_WIRINGPI_ISR Error at wiringPiISR, Unable to setup Input isr",
    14: "HTI_ERR_EPOS_INIT openEPOS() failure",
    15: "HTI_ERR_UNKNOWN_CMD Unknown command received. Typo or transmission error.",
    16: "HTI_ERR_FILE_NOT_FOUND",
    17: "HTI_ERR_SYNTAX_IN_PROGRAM",
    18: "HTI_ERR_STEPROCKER_HOMING - SENSOR",
    19: "HTI_ERR_WIRINGPI_I2C_SETUP",
    20: "HTI_ERR_WIRINGPI_I2C_READ",
    21: "HTI_ProgEnd Successful prog or servprog execution",
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
    log: Callable[..., None] = field(default_factory=lambda: Machine.default_log)

    def write(self, line: str):
        msg = line.strip().encode() + b'\r\n'
        self.log(f'bluewash.write({msg!r})')
        self.com.write(msg)

    def read(self) -> str:
        reply_bytes: bytes = self.com.readline()
        self.log(f'bluewash.read() = {reply_bytes!r}')
        reply = reply_bytes.decode().strip()
        return reply

    def read_until_code(self) -> Tuple[int, List[str]]:
        out: list[str] = []
        while True:
            reply = self.read()
            if reply.startswith('Err='):
                return int(reply[len('Err='):]), out
            elif reply:
                out += [reply]

    def read_until_prog_end(self) -> List[str]:
        # Err=00 is OK, read until Err=21
        out: List[str] = []
        while True:
            code, lines = self.read_until_code()
            out += lines
            self.check_code(code, HTI_NoError, HTI_ProgEnd)
            if code == HTI_ProgEnd:
                return out

    def get_progs(self) -> Set[int]:
        self.write(f'$getprogs')
        code, lines = self.read_until_code()
        self.check_code(code, HTI_NoError)
        res = {
            int(line.split()[0])
            for line in lines
            if line and line[0].isdigit()
        }
        return res

    def delete_prog(self, index: int):
        progs = self.get_progs()
        if index in progs:
            self.write(f'$deleteprog {index:02}')
            code, _ = self.read_until_code()
            self.check_code(code, HTI_NoError, HTI_ERR_FILE_NOT_FOUND)

    def write_prog(self, program_code: str, index: int):
        self.delete_prog(index)
        lines = program_code.splitlines(keepends=False)
        self.write(f'$Copyprog {index:02} _')
        for line in lines:
            self.write('$& ' + line)
        self.write('$%')
        code, _ = self.read_until_code()
        self.check_code(code, HTI_NoError)

        '''
        Dong Liang at BlueCatBio:

            Please execute once the command "getprogs" after the "copyprog" in your
            "validate" command. This "getprogs" forces BlueWasher to refresh
            the programs onboard and may get avoid for such rare case,
            that your program is not completely "copied".
        '''
        self.get_progs()

    def check_code(self, code: int, *ok_codes: int) -> None:
        if code not in ok_codes:
            raise ValueError(f'Unexpected reply from BlueWash: {code=} {Errors.get(code, "unknown error")}')

@dataclass(frozen=True)
class BlueWash(Machine):
    root_dir: str
    com_port: str = 'COM6'

    @contextlib.contextmanager
    def _connect(self):
        with self.exclusive():
            self.log('bluewash: Using com_port', self.com_port)
            with self.timeit('_connection'):
                com = Serial(
                    self.com_port,
                    timeout=15,
                    baudrate=115200
                )
                conn = ConnectedBlueWash(com, log=self.log)

                '''
                The BlueWasher has two different protocols, one verbose
                mode and one automation-friendly mode which only replies
                the error code. We make sure we are in the automation-friendly
                mode by always sending "$changelog 0".
                '''
                conn.write('$changelog 0')
                code, _lines = conn.read_until_code()
                if code != 0:
                    raise ValueError('Expected code Err=00, received {code=}')

                yield conn
                com.close()

    def init_all(self):
        '''
        Initializes linear drive, rotor, inputs, outputs, motors, valves.
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

    def run_cmd(self, *cmd_parts: str):
        with self._connect() as con:
            con.write(' '.join(map(str, cmd_parts)))
            code, lines = con.read_until_code()
            con.check_code(code, HTI_NoError)
            return lines

    def run_servprog(self, index: int):
        with self._connect() as con:
            with self.timeit('runservprog'):
                con.write(f'$runservprog {index}')
                return con.read_until_prog_end()

    def run_prog(self, index: int):
        with self._connect() as con:
            with self.timeit('runprog'):
                con.write(f'$runprog {index}')
                return con.read_until_prog_end()

    def run_from_file(self, *filename_parts: str):
        with self._connect() as con:
            filename = '/'.join(filename_parts)
            path = Path(self.root_dir) / filename
            text = path.read_text()
            lines = unroll_loops(text)
            self.log('\n'.join(lines), lines=lines)
            for line in lines:
                if line.startswith('#'):
                    self.log(f'               {line}')
                    continue
                con.write(line)
                code, _lines = con.read_until_code()
                con.check_code(code, HTI_NoError)

    def write_prog(self, program_text: str, index: int):
        program_text = textwrap.dedent(program_text).strip()
        with self._connect() as con:
            with self.timeit('copyprog'):
                con.write_prog(program_text, index)

    def TestCommunications(self):
        with self.exclusive():
            program: str = '''
                $getserial
                $getfirmware
                $getipadr
            '''
            self.write_prog(program, index=98)
            return self.run_prog(index=98)

    mem: Dict[int, str] = field(default_factory=dict)

    def Validate(self, *filename_parts: str):
        with self.exclusive():
            filename = '/'.join(filename_parts)
            self.mem[99] = filename
            path = Path(self.root_dir) / filename
            self.write_prog(path.read_text(), index=99)

    def RunValidated(self, *filename_parts: str) -> List[str]:
        with self.exclusive():
            filename = '/'.join(filename_parts)
            stored = self.mem.get(99)
            if stored == filename:
                return self.run_prog(index=99)
            else:
                self.log(f'warning: RunValidated without Validate first', type='warning', stored=stored, filename=filename)
                self.log(f'{stored=!r}')
                self.log(f'{filename=!r}')
                return self.Run(*filename_parts)

    def Run(self, *filename_parts: str) -> List[str]:
        with self.exclusive():
            self.Validate(*filename_parts)
            return self.RunValidated(*filename_parts)

def unroll_loops(text: str) -> list[str]:
    lines = [s.strip() for s in text.splitlines(keepends=False)]
    lines = fix(unroll_one, lines)
    return lines

A = TypeVar('A')

def fix(f: Callable[[A], A], x: A):
    while True:
        fx = f(x)
        if fx == x:
            return x
        else:
            x = fx

def unroll_one(lines: list[str]):
    for i, line in enumerate(lines):
        if line.startswith('loop '):
            n = int(line[5:])
            for j, end_line in enumerate(lines):
                if j > i and end_line == 'endloop':
                    return lines[:i] + lines[i+1:j] * n + lines[j+1:]
            raise ValueError('loop without endloop')
    return lines

