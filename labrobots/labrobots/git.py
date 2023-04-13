from __future__ import annotations
from typing import *
from dataclasses import *

from subprocess import check_output, run

from .machine import Machine

import functools

@functools.cache
def git_head_show_at_startup():
    try:
        return (
            check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            check_output(['git', 'show', '--stat'], text=True).strip(),
        )
    except Exception as e:
        return (str(e), str(e))

git_head_show_at_startup()

@dataclass(frozen=True)
class Git(Machine):
    def head(self) -> str:
        '''git rev-parse HEAD'''
        return check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()

    def head_at_startup(self) -> str:
        '''git rev-parse HEAD` when process started'''
        return git_head_show_at_startup()[0]

    def show(self) -> list[str]:
        '''git show --stat'''
        return check_output(['git', 'show', '--stat'], text=True).strip().splitlines()

    def show_at_startup(self) -> list[str]:
        '''`git show` when process started'''
        return git_head_show_at_startup()[1].splitlines()

    def branch(self) -> str:
        '''git branch --show-current'''
        return check_output(['git', 'branch', '--show-current'], text=True).strip()

    def status(self) -> list[str]:
        '''git status -s'''
        return check_output(['git', 'status', '-s'], text=True).strip().splitlines()

    def checkout(self, branch: str):
        '''git checkout -B {branch}; git branch --set-upstream-to origin/{branch} {branch}; git pull && kill -TERM {os.getpid()}'''
        self.log(res := run(['git', 'fetch'], text=True, capture_output=True))
        res.check_returncode()
        self.log(res := run(['git', 'checkout', '-B', branch], text=True, capture_output=True))
        res.check_returncode()
        self.log(res := run(['git', 'branch', '--set-upstream-to', f'origin/{branch}', branch], text=True, capture_output=True))
        res.check_returncode()
        self.pull_and_shutdown()

    def pull_and_shutdown(self):
        '''git pull && kill -TERM {os.getpid()}'''
        self.log(res := check_output(['git', 'pull'], text=True))
        if res.strip() != 'Already up to date.':
            self.shutdown()

    def shutdown(self):
        '''kill -TERM {os.getpid()}'''
        import os
        import signal
        self.log('killing process...')
        os.kill(os.getpid(), signal.SIGTERM)
        self.log('killed.')

