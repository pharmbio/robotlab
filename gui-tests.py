from typing import *
from contextlib import contextmanager
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT
from threading import RLock
from threading import Timer, Thread
from urllib.request import urlopen
import atexit
import os
import pprint
import shlex
import signal
import sys
import time

def main():
    with chdir('cellpainter'):
        test('cellpainter-gui --dry-run',              'http://localhost:5000',                        'incubation times:')
        test('cellpainter-moves --dry-run',            'http://localhost:5000',                        'wash_to_disp')
        test('cellpainter --cell-paint 2 --visualize', 'http://localhost:5000',                        'plate  1 incubation')
        test('cellpainter --cell-paint 2 --visualize', 'http://localhost:5000?cmdline=--cell-paint+3', 'plate  3 incubation')

    with chdir('imager'):
        test('pf-moves --dry-run', 'http://localhost:5000',             'fridge-to-H12')
        test('imager-gui',         'http://localhost:5051?page=system', 'test-comm:')

    test('labrobots --test', 'http://localhost:5050/echo/echo?apa=1.2&bepa=true&cepa=[3,4]',
                             "echo () {'apa': 1.2, 'bepa': True, 'cepa': [3, 4]}")
    test('labrobots --test', 'http://localhost:5050/echo/error?depa=oops',
                             "ValueError: error () {'depa': 'oops'}")

    print('success!')

@contextmanager
def chdir(path: str, __pwd_lock: RLock = RLock()):
    at_begin = os.getcwd()
    with __pwd_lock:
        try:
            os.chdir(path)
            yield
        finally:
            os.chdir(at_begin)

def curl(url: str) -> Any:
    ten_minutes = 60 * 10
    res = urlopen(url, timeout=ten_minutes).read().decode()
    return res

@contextmanager
def popen(cmd: Union[str, list[str]]):
    try:
        p = Popen(cmd, stdout=PIPE, stderr=STDOUT, bufsize=1, universal_newlines=True)
        @atexit.register
        def kill_p():
            p.kill()
            p.wait()
        t = Timer(5, lambda: [print('timeout, killing process...'), kill_p(), print('process killed.')])
        t.start()
        yield p
    finally:
        print('terminating process')
        assert p           # type: ignore
        p.terminate()
        exitcode = p.wait()
        print(f'exitcode: {exitcode}')
        assert kill_p      # type: ignore
        atexit.unregister(kill_p)
        t.cancel()
        assert p.stdout
        for line in p.stdout:
            print(f'line: {line.rstrip()!r}')
        assert exitcode == -15

def test(cmd: str, addr: str, needle: str):
    wait_for = 'Serving Flask app'
    print('=' * 80)
    print(cmd)
    with popen(shlex.split(cmd)) as p:
        assert p.stdout
        for line in p.stdout:
            print(f'line: {line.rstrip()!r}')
            if wait_for in line:
                time.sleep(0.1)
                print(f'curl {addr!r}')
                res = curl(addr)
                if needle in res:
                    print(f'found {needle!r} as expected:')
                    pos = res.index(needle)
                    print(repr(res[pos-6:][:75]))
                    return
                else:
                    pprint.pp(res.splitlines()[:20])
                    print(f'fail! did not find {needle!r} in {addr!r} of {cmd!r}')
                    sys.exit(1)
        print(f'did not reach {wait_for!r} from server')
        sys.exit(1)

if __name__ == '__main__':
    main()
