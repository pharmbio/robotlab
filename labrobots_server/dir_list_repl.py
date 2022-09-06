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
            elif d['cmd'] == 'hts_mod':
                assert enable_write_file
                experiment_set = d['experiment_set']
                experiment_base_name = d['experiment_base_name']
                full_path = (root / Path(d['path'])).resolve()
                rel_path = full_path.relative_to(root)
                lines = full_path.read_bytes().splitlines(keepends=True)
                assert lines[1].startswith(b'"stExperimentSet", "'), lines[:3]
                assert lines[2].startswith(b'"stDataFile", "'), lines[:3]
                assert lines[1].endswith(b'"\r\n'), lines[:3]
                assert lines[2].endswith(b'"\r\n'), lines[:3]
                lines[1] = f'"stExperimentSet", "{experiment_set}"\r\n'.encode('ascii')
                lines[2] = f'"stDataFile", "{experiment_base_name}"\r\n'.encode('ascii')
                assert lines[1].startswith(b'"stExperimentSet", "'), lines[:3]
                assert lines[2].startswith(b'"stDataFile", "'), lines[:3]
                assert lines[1].endswith(b'"\r\n'), lines[:3]
                assert lines[2].endswith(b'"\r\n'), lines[:3]
                # now save it in the same dir but with a new filename based on base name
                for i in range(10000):
                    si = f' ({i})' if i else ''
                    new_full_path = full_path.with_name(experiment_base_name + si + '.HTS')
                    new_rel_path = new_full_path.relative_to(root)
                    if not new_full_path.exists():
                        new_full_path.write_bytes(b''.join(lines))
                        print('value', json.dumps({
                            'path': str(new_rel_path).replace('\\', '/'),
                            'full': str(new_full_path),
                        }))
                        break
                else:
                    print('error could not make a filename for file')
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
