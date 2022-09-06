from argparse import ArgumentParser

from pathlib import Path
from datetime import datetime
# from hashlib import sha256
from typing import List, Any

import json
import sys

def main():
    parser = ArgumentParser('labrobots_dir_list_repl')
    parser.add_argument('--enable-write-file', action='store_true')
    parser.add_argument('--root-dir', type=str, required=True)
    parser.add_argument('--extension', type=str, required=True)
    args = parser.parse_args(sys.argv[1:])
    root_dir = args.root_dir
    ext = args.extension.strip('.')
    root = Path(root_dir).resolve()
    dir_list_repl(root, ext, args.enable_write_file)

def dir_list_repl(root: Path, ext: str, enable_write_file: bool=False):
    print('message', locals())
    while True:
        print('ready')
        action_str = input()
        print('message', action_str)

        try:

            if action_str.strip() in ('', 'list'):
                d: dict[str, Any] = {'cmd': 'list'}
            else:
                d: dict[str, Any] = json.loads(action_str)

            print('message', d)

            if d['cmd'] == 'list':
                value: List[dict[str, str]] = []
                for lhc in root.glob(f'**/*.{ext}'):
                    path = str(lhc.relative_to(root)).replace('\\', '/')
                    mtime = lhc.stat().st_mtime
                    modified = str(datetime.fromtimestamp(mtime).replace(microsecond=0))
                    value += [{
                        'path': path,
                        'full': str(lhc.resolve()),
                        'modified': modified,
                        # 'sha256': sha256(lhc.read_bytes()).hexdigest(),
                    }]
                print('value', json.dumps(value))
            elif d['cmd'] == 'read':
                full_path = (root / Path(d['path'])).resolve()
                rel_path = full_path.relative_to(root)
                print('value', json.dumps({
                    'path': str(rel_path).replace('\\', '/'),
                    'full': str(full_path),
                    'contents': full_path.read_text(),
                }))
            elif d['cmd'] == 'write':
                assert enable_write_file
                full_path = (root / Path(d['path'])).resolve()
                rel_path = full_path.relative_to(root)
                contents = d['contents']
                assert not full_path.exists()
                full_path.write_text(contents)
                print('value', json.dumps({
                    'path': str(rel_path).replace('\\', '/'),
                    'full': str(full_path),
                    'contents': full_path.read_text(),
                }))
            else:
                print('message no such command')
                print('error')
                continue
            print('success')

        except:
            import traceback as tb
            print(tb.format_exc())
            print('error')
