from dataclasses import *
from typing import *

import labrobots
from labrobots.dir_list import PathInfo
from .log import Log, DB

import pbutils
import base64
import re

def nonempty(*xs: str) -> list[str]:
    return [x for x in sorted(set(xs)) if x]

@dataclass(frozen=True)
class ProtocolPaths:
    '''
    The number of steps is either
        - 5: mito, pfa, triton, stains, final wash
        - 6: mito, pfa, triton, stains, extra wash, final wash (with --two-final-washes)

    For each batch:
        Run the protocols in wash_prime
        For each step i:
            Run disp_prime[i]
            For each plate:
                Run wash_5[i] if number of steps is 5
                Run wash_6[i] if number of steps is 6
                Run disp_prep[i] (starts when plate is still in washer)
                Run disp_main[i]

    The prefixes looked for in a directory are listed in template_protocol_paths below.
    All files are optional: for each prefix without a corresponding file this run is just skipped.
    '''
    wash_prime: list[str]
    wash_5:     list[str]
    wash_6:     list[str]
    disp_prime: list[str]
    disp_prep:  list[str]
    disp_main:  list[str]
    blue_prime: list[str]
    blue:       list[str]

    def all_wash_paths(self) -> list[str]:
        return nonempty(*self.wash_prime, *self.wash_5, *self.wash_6)

    def all_disp_paths(self) -> list[str]:
        return nonempty(*self.disp_prime, *self.disp_prep, *self.disp_main)

    def all_blue_paths(self) -> list[str]:
        return nonempty(*self.blue_prime, *self.blue)

    def use_wash(self) -> bool:
        return any(self.all_wash_paths())

    def use_blue(self) -> bool:
        return any(self.all_blue_paths())

    def empty(self) -> bool:
        return not any([
            *self.all_wash_paths(),
            *self.all_blue_paths(),
            *self.all_disp_paths(),
        ])

template_protocol_paths = ProtocolPaths(
    wash_prime = [
        '0_W_.*.LHC',
    ],
    wash_5 = [
        '1_W_.*.LHC',
        '3_W_.*.LHC',
        '5_W_.*.LHC',
        '7_W_.*.LHC',
        '9_W_.*.LHC',
    ],
    wash_6 = [
        '1_W_.*.LHC',
        '3_W_.*.LHC',
        '5_W_.*.LHC',
        '7_W_.*.LHC',
        '9_10_W_.*.LHC',
        '9_10_W_.*.LHC',
    ],
    disp_prime = [
        '2.0_D_.*.LHC',
        '4.0_D_.*.LHC',
        '6.0_D_.*.LHC',
        '8.0_D_.*.LHC',
    ],
    disp_prep = [
        '2.0b_D_.*.LHC',
        '4.0b_D_.*.LHC',
        '6.0b_D_.*.LHC',
        '8.0b_D_.*.LHC',
    ],
    disp_main = [
        '2.1_D_.*.LHC',
        '4.1_D_.*.LHC',
        '6.1_D_.*.LHC',
        '8.1_D_.*.LHC',
    ],
    blue_prime = [
        '0_W_.*.prog',
    ],
    blue = [
        '1_W_.*.prog',
        '3_W_.*.prog',
        '5_W_.*.prog',
        '7_W_.*.prog',
        '9_W_.*.prog',
    ],
)

pbutils.serializer.register(globals())

class Response(TypedDict):
    value: list[PathInfo]

def get_protocol_paths() -> dict[str, ProtocolPaths]:
    return {
        k: v
        for k, v in pbutils.serializer.read_json('protocol_paths.json').items()
        if k not in skip
    }

skip = set('''
    automation_prep
    automation
    automation_onlyDAPI
    automation_onlyMITO
    automation_v5.0_AW_CR_noMito
    bloop
    BlueWasher
    dan-test
    demo
    generic-384-painting
    generic-96-painting
    jordi
    test-protocols
    automation_v2
    automation_v3
    automation_v3.1
    automation_v3.2
'''.split())

def update_protocol_paths() -> list[PathInfo]:
    path_infos = labrobots.WindowsNUC().remote(timeout_secs=10).dir_list.list()
    res: dict[str, ProtocolPaths] = {}
    for protocol_dir, infos in sorted(pbutils.group_by(path_infos, lambda info: info['path'].partition('/')[0]).items()):
        if protocol_dir in skip:
            # print('Skipping', protocol_dir)
            continue
        protocol_paths = make_protocol_paths(protocol_dir, infos)
        if not protocol_paths.empty():
            res[protocol_dir] = protocol_paths
            # print('Adding', protocol_dir)
    pbutils.serializer.write_json(res, 'protocol_paths.json', indent=2)
    return path_infos

def paths_v5():
    return get_protocol_paths()['automation_v5.0']

def make_protocol_paths(protocol_dir: str, infos: list[PathInfo]):
    protocol_dir = protocol_dir.rstrip('/')

    lhcs: list[str] = []
    for info in infos:
        dir, _, lhc = info['path'].partition('/')
        if dir == protocol_dir:
            lhcs += [lhc]

    def resolve_one(regex: str) -> str:
        candidates = [
            protocol_dir + '/' + lhc
            for lhc in lhcs
            if re.match(regex + '$', lhc)
        ]
        if len(candidates) > 1:
            raise ValueError(f'More than one candidate for {regex=}: {candidates}')
        elif candidates:
            return candidates[0]
        else:
            return ''

    def resolve(regexes: list[str]) -> list[str]:
        return [resolve_one(regex) for regex in regexes]

    paths = ProtocolPaths(
        **{
            k: resolve(v)
            for k, v in asdict(template_protocol_paths).items()
        }
    )
    return paths

def add_protocol_dir_as_sqlar(db: DB, protocol_dir: str):
    '''
    Add the LHC files in the protocol_dir as an SQLite Archive (sqlar) table (without compression for simplicity)
    '''
    files = labrobots.WindowsNUC().remote(timeout_secs=60).dir_list.read_files(protocol_dir)
    with db.transaction:
        for f in files:
            data: bytes = base64.b64decode(f['data_b64'])
            Log(db).sqlar_add(f['name'], f['mtime'], data)
