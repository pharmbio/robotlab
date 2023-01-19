from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime

from .log import CommandWithMetadata, Metadata
from .commands import BiotekAction

def execute(
    runtime: Runtime,
    entry: CommandWithMetadata,
    machine: Literal['wash', 'disp'],
    protocol_path: str | None,
    action: BiotekAction = 'Run',
):
    '''
    Repeatedly try to run the protocol until it succeeds or we get an unknown error.

    Success looks like this:

        {
          "lines": [
            "message protocol begin",
            "message protocol done",
            "status 1",
            "message 1 - eOK",
            "success"
          ],
          "success": True
        }

    Acceptable failure looks like this:

        {
          "lines": [
            "message ErrorCode: 24673, ErrorString: Error code: 6061",
            "Port is no longer available",
            "error System.Exception: Exception calling cLHC method: LHC_TestCommunications, ErrorCode: 24673, ErrorString: Error code: 6061",
            "Port is no longer available",
            "at LHCCallerCLI.Program.handleRetCodeErrors(Int16 retCode, String calledMethod) in C:\\pharmbio\\robotlab-labrobots\\biotek-cli\\LHC_CallerCLI\\Program.cs:line 273",
            "at LHCCallerCLI.Program.LHC_TestCommunications() in C:\\pharmbio\\robotlab-labrobots\\biotek-cli\\LHC_CallerCLI\\Program.cs:line 263",
            "at LHCCallerCLI.Program.HandleMessage(String cmd, String arg, String path_prefix) in C:\\pharmbio\\robotlab-labrobots\\biotek-cli\\LHC_CallerCLI\\Program.cs:line 148",
            "at LHCCallerCLI.Program.Loop(String path_prefix) in C:\\pharmbio\\robotlab-labrobots\\biotek-cli\\LHC_CallerCLI\\Program.cs:line 138"
          ],
          "success": False
        }

    Failure looks like this:

        {
          "lines": [
            "error last validated protocol and argument does not match"
          ],
          "success": False
        }

    '''
    if machine == 'wash':
        biotek = runtime.wash
    elif machine == 'disp':
        biotek = runtime.disp
    else:
        raise ValueError(f'No such biotek {machine=}')
    while True:
        if biotek is None:
            est = entry.metadata.est
            assert isinstance(est, float)
            runtime.sleep(est, entry.merge(Metadata(dry_run_sleep=True)))
            res: Any = {"success":True, "lines":[]}
        else:
            match action:
                case 'Run':
                    assert isinstance(protocol_path, str)
                    res = biotek.Run(*protocol_path.split('/'))
                case 'Validate':
                    assert isinstance(protocol_path, str)
                    res = biotek.Validate(*protocol_path.split('/'))
                case 'RunValidated':
                    assert isinstance(protocol_path, str)
                    res = biotek.RunValidated(*protocol_path.split('/'))
                case 'TestCommunications':
                    assert protocol_path is None
                    res = biotek.TestCommunications()
                case _:
                    raise ValueError(f'No such biotek {action=}')
        success: bool = res.get('success', False)
        lines: list[str] = res.get('lines', [])
        details = '\n'.join(lines)
        if success:
            break
        elif 'Error code: 6061' in details:
            runtime.log(entry.message(msg=f'{machine}: {details}'))
            runtime.log(entry.message(msg=f'{machine} got error code 6061, retrying...'))
        else:
            runtime.log(entry.message(f'{machine}: {details}', is_error=True))
            raise ValueError(res)
