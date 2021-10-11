from __future__ import annotations
from dataclasses import *
from typing import *
from typing_extensions import TypeAlias

from runtime import Runtime, RuntimeConfig, curl
import timings

BiotekCommand: TypeAlias = Literal[
    'RunProtocol',
    'ValidateProtocol',
    'RunLastValidatedProtocol',
    'TestCommunications',
]

def execute(
    runtime: Runtime,
    machine: Literal['wash', 'disp'],
    protocol_path: str | None,
    cmd: BiotekCommand = 'RunProtocol',
    metadata: dict[str, Any] = {},
):
    '''
    Repeatedly try to run the protocol until it succeeds or we get an unknown error.

    Success looks like this:

        {"success": True, "lines": []}

    Acceptable failure looks like this:

        {"success": False, "lines": [
            [1.234, "Message - Exception calling cLHC method:"]
            [1.234, "LHC_TestCommunications, ErrorCode: 24673, ErrorString: Error code: 6061"
            [1.234, "Port is no longer available - ..."]
        ]}

    Failure looks like this:

        {"success": False, "lines": []}
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
            lines: list[tuple[float, str]] = res.get('lines', [])
            details = '\n'.join(line for _, line in lines)
            if success:
                break
            elif 'Error code: 6061' in details and 'Port is no longer available' in details:
                runtime.log('warn', machine, 'got error code 6061, retrying...', {**metadata, **res})
            else:
                print(details)
                raise ValueError(res)
