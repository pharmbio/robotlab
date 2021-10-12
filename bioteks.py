from __future__ import annotations
from dataclasses import *
from typing import *

from runtime import Runtime, RuntimeConfig, curl
import timings

BiotekCommand = Literal[
    'Run',
    'Validate',
    'RunValidated',
    'TestCommunications',
]

def execute(
    runtime: Runtime,
    machine: Literal['wash', 'disp'],
    protocol_path: str | None,
    cmd: BiotekCommand = 'Run',
    metadata: dict[str, Any] = {},
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
    if cmd == 'TestCommunications':
        log_arg: str = cmd
    else:
        assert protocol_path
        log_arg: str = cmd + ' ' + protocol_path
    with runtime.timeit(machine, log_arg, metadata=metadata):
        while True:
            if runtime.config.disp_and_wash_mode == 'noop':
                est = timings.estimate(machine, log_arg)
                runtime.log('info', machine, f'pretending to run for {round(est, 2)}s', metadata)
                runtime.sleep(est)
                res: Any = {"success":True,"lines":[]}
            else:
                url = (
                    runtime.env.biotek_url +
                    '/' + machine +
                    '/' + cmd +
                    '/' + (protocol_path or '')
                )
                url = url.rstrip('/')
                res: Any = curl(url)
            success: bool = res.get('success', False)
            lines: list[str] = res.get('lines', [])
            details = '\n'.join(lines)
            if success:
                break
            elif 'Error code: 6061' in details and 'Port is no longer available' in details:
                runtime.log('warn', machine, 'got error code 6061, retrying...', {**metadata, **res})
            else:
                print(details)
                raise ValueError(res)
