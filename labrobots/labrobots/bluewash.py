from typing import *
from serial import Serial, SerialException # type: ignore
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
HTI_ERR_UNKNOWN_CMD = 15

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

    def read_until_code(self) -> Tuple[int | str, List[str]]:
        out: list[str] = []
        while True:
            reply = self.read()
            if reply.startswith('Err='):
                return int(reply[len('Err='):]), out
            if reply.startswith('STATUS='):
                return reply, out
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
        lines = program_code.splitlines()
        self.write(f'$Copyprog {index:02} _')
        for line in lines:
            if line.strip().startswith('#'):
                continue
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

    def check_code(self, code: int | str, *ok_codes: int | str) -> None:
        if code not in ok_codes:
            if isinstance(code, int):
                raise ValueError(f'Unexpected reply from BlueWash: {code=} {Errors.get(code, f"unknown {code=}")}')
            else:
                raise ValueError(f'Unexpected reply from BlueWash: {code=}')

@dataclass(frozen=True)
class BlueWash(Machine):
    root_dir: str
    com_port: str = 'COM6'

    @contextlib.contextmanager
    def _connect(self):
        with self.exclusive():
            self.log('bluewash: Using com_port', self.com_port)
            with self.timeit('_connection'):
                '''
                Retry loop to get a communication.

                Communication fails sometimes (at about 20%) when communicating
                with a biotek machine at the same time as the blue washer.
                '''
                com = None
                errors: list[SerialException] = []
                for num_retry in range(10):
                    try:
                        com = Serial(
                            self.com_port,
                            timeout=15,
                            baudrate=115200
                        )
                    except SerialException as e:
                        self.log(f'bluewash: {e}', error=str(e), error_repr=repr(e), num_retry=num_retry)
                        time.sleep(0.1)
                        errors += [e]
                        continue
                    else:
                        break
                if com is None:
                    if errors:
                        msg = f'Failed to communicate with the blue washer: {errors[-1]}.'
                    else:
                        msg = f'Failed to communicate with the blue washer.'
                    msg += ' Please make sure the blue washer GUI is turned off.'
                    raise ValueError(msg)
                conn = ConnectedBlueWash(com, log=self.log)

                '''
                The BlueWasher has two different protocols, one verbose
                mode and one automation-friendly mode which only replies
                the error code. We make sure we are in the automation-friendly
                mode by always sending "$changelog 0".
                '''
                conn.write('$changelog 0')
                code, _lines = conn.read_until_code()
                conn.check_code(code, HTI_NoError)
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
            con.check_code(code, HTI_NoError, 'STATUS=00', 'STATUS=01', 'STATUS=02', 'STATUS=03')
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

    def run_program(self, program_text: str):
        with self._connect() as con:
            program_text = textwrap.dedent(program_text).strip()
            lines = unroll_loops(program_text)
            self.log('\n'.join(lines), lines=lines)
            for line in lines:
                if line.startswith('#'):
                    continue
                while True:
                    time.sleep(0.05) # Manual says sleep at least 50ms between commands
                    con.write('$' + line.lstrip('$'))
                    code, _lines = con.read_until_code()
                    con.check_code(code, HTI_NoError, HTI_ERR_UNKNOWN_CMD)

                    if code == HTI_ERR_UNKNOWN_CMD:
                        # If transmission fails you get Err=15. Then we retry.
                        pass
                    elif code == HTI_NoError:
                        break

    def run_from_file(self, *filename_parts: str):
        filename = '/'.join(filename_parts)
        path = Path(self.root_dir) / filename
        program_text = path.read_text()
        self.run_program(program_text)

    def write_prog(self, program_text: str, index: int):
        program_text = textwrap.dedent(program_text).strip()
        with self._connect() as con:
            with self.timeit('copyprog'):
                con.write_prog(program_text, index)

    def TestCommunications(self):
        program_text: str = '''
            $getserial
            $getfirmware
            $getipadr
        '''
        self.run_program(program_text)

    def Validate(self, *filename_parts: str):
        filename = '/'.join(filename_parts)
        self.log(f'deprecation warning: Validate is now unnecessary for bluewasher', type='warning', filename=filename, filename_parts=filename_parts)

    def RunValidated(self, *filename_parts: str):
        filename = '/'.join(filename_parts)
        self.log(f'deprecation warning: RunValidated is now unnecessary for bluewasher, use Run instead', type='warning', filename=filename, filename_parts=filename_parts)
        self.Run(*filename_parts)

    def Run(self, *filename_parts: str):
        self.run_from_file(*filename_parts)

def unroll_loops(text: str) -> list[str]:
    lines = text.splitlines()
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
    '''
    Unrolls the last innermost loop
    '''
    for i, line in reversed(list(enumerate(lines))):
        line = line.strip()
        if line.startswith('loop '):
            n = int(line[5:])
            for j, end_line in enumerate(lines):
                end_line = end_line.strip()
                if j > i and end_line == 'endloop':
                    return lines[:i] + lines[i+1:j] * n + lines[j+1:]
            raise ValueError('loop without endloop')
    return lines

def test_unroll():
    assert unroll_one([
        'a',
        'loop 3',
        'b',
        'endloop',
        'c',
    ]) ==  [
        'a',
        'b',
        'b',
        'b',
        'c',
    ]

    assert unroll_one([
        'a',
        'loop 3',
        'b1',
        'endloop',
        'loop 3',
        'b2',
        'endloop',
        'c',
    ]) ==  [
        'a',
        'loop 3',
        'b1',
        'endloop',
        'b2',
        'b2',
        'b2',
        'c',
    ]

    assert unroll_one([
        'a',
        'loop 2',
        '[',
        'loop 2',
        'b',
        'endloop',
        ']',
        'endloop',
        'c',
    ]) ==  [
        'a',
        'loop 2',
        '[',
        'b',
        'b',
        ']',
        'endloop',
        'c',
    ]

    assert unroll_loops('\n'.join([
        'a',
        'loop 2',
        '[',
        'loop 2',
        'b',
        'endloop',
        ']',
        'endloop',
        'c',
    ])) ==  [
        'a',
        '[',
        'b',
        'b',
        ']',
        '[',
        'b',
        'b',
        ']',
        'c',
    ]
