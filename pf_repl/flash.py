from __future__ import annotations
from typing import *

from pathlib import Path
from ftplib import FTP
import io
import os
import shlex

DEFAULT_HOST='10.10.0.98'

def ftp_store(ftp: FTP, filename: str, data: bytes):
    ftp.storbinary(f'STOR {filename}', io.BytesIO(data))

def flash(fifo_file: str='pf23.fifo', host: str=DEFAULT_HOST, port: int=23):
    if isinstance(port, str):
        port = int(port)
    fifo_path = Path(fifo_file)
    if fifo_path.exists() and not fifo_path.is_fifo():
        raise ValueError(f'{fifo_path} exists but is not a fifo.')
    elif not fifo_path.exists():
        os.mkfifo(fifo_path)
    print(f'''
        Using {fifo_path} as fifo. If the fifo is not connected then run:

            tail -f {fifo_path} | nc {host} {port}

        When done you can send quit and then close nc:

            >>{fifo_path} echo quit

        The rest of this program outputs commands corresponding to its communication on the fifo.
    ''')

    def send(s: str, comment: str = ''):
        if comment:
            comment = f' # {comment}'
        print(f'>>{fifo_path} echo {shlex.quote(s)}{comment}')
        with open(fifo_path, 'a') as fp:
            print(s, file=fp)

    send('Help', 'this is the default password')

    project = Path('Tcp_cmd_server')
    assert project.is_dir(), f'Path {project} is missing or not a directory'
    dir = f'/flash/projects/{project}'
    send(f'stop -all')
    send(f'unload -all')
    send(f'execute File.CreateDirectory("{dir}")')
    with FTP(host) as ftp:
        ftp.login()
        for path in project.glob('*.gp*'):
            print(f'# ftp_store: {path.name}')
            ftp_store(ftp, f'{dir}/{path.name}', path.read_bytes())
    send(f'load {dir} -compile')
    send(f'execute StartMain()')

if __name__ == '__main__':
    import sys
    flash(*sys.argv[1:]) # type: ignore
