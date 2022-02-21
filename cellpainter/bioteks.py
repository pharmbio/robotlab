from __future__ import annotations
from dataclasses import *
from typing import *

from .runtime import Runtime

from .log import Metadata, LogEntry, Error
from .commands import BiotekAction
from .utils import curl

def execute(
    runtime: Runtime,
    entry: LogEntry,
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
    while True:
        if runtime.config.disp_and_wash_mode == 'noop':
            est = entry.metadata.est
            assert isinstance(est, float)
            runtime.sleep(est, entry.add(Metadata(dry_run_sleep=True)))
            res: Any = {"success":True, "lines":[]}
        else:
            assert runtime.config.disp_and_wash_mode == 'execute'
            url = (
                runtime.env.biotek_url +
                '/' + machine +
                '/' + action +
                '/' + (protocol_path or '')
            )
            url = url.rstrip('/')
            res: Any = curl(url)
        success: bool = res.get('success', False)
        lines: list[str] = res.get('lines', [])
        details = '\n'.join(lines)
        if success:
            break
        elif 'Error code: 6061' in details:
            for line in lines:
                runtime.log(entry.add(msg=f'{machine}: {line}'))
            runtime.log(entry.add(msg=f'{machine} got error code 6061, retrying...'))
        else:
            for line in lines or ['']:
                runtime.log(entry.add(err=Error(f'{machine}: {line}')))
            raise ValueError(res)
