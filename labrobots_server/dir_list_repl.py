from argparse import ArgumentParser

from pathlib import Path
from datetime import datetime
from hashlib import sha256
from typing import List

import json
import sys

def main():
    parser = ArgumentParser('labrobots_dir_list_repl')
    parser.add_argument('--root-dir', type=str, required=True)
    parser.add_argument('--extension', type=str, required=True)
    args = parser.parse_args(sys.argv[1:])
    root_dir = args.root_dir
    ext = args.extension.strip('.')
    root = Path(root_dir)
    dir_list_repl(root, ext)

def dir_list_repl(root: Path, ext: str):
    while True:
        print("ready")
        _ = input()
        value: List[dict[str, str]] = []
        for lhc in root.glob(f'*/*.{ext}'):
            path = str(lhc.relative_to(root)).replace('\\', '/')
            mtime = lhc.stat().st_mtime
            modified = str(datetime.fromtimestamp(mtime).replace(microsecond=0))
            value += [{
                'path': path,
                'modified': modified,
                'sha256': sha256(lhc.read_bytes()).hexdigest(),
            }]
        print("value", json.dumps(value))
        print("success")
