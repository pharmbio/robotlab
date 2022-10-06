from dataclasses import dataclass, asdict
from typing import TypedDict
from .utils import curl
from . import utils

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

    def all_wash_paths(self) -> list[str]:
        return nonempty(*self.wash_prime, *self.wash_5, *self.wash_6)

    def all_disp_paths(self) -> list[str]:
        return nonempty(*self.disp_prime, *self.disp_prep, *self.disp_main)

template_protocol_paths = ProtocolPaths(
    wash_prime = [
        '0_W_',
    ],
    wash_5 = [
        '1_W_',
        '3_W_',
        '5_W_',
        '7_W_',
        '9_W_',
    ],
    wash_6 = [
        '1_W_',
        '3_W_',
        '5_W_',
        '7_W_',
        '9_10_W_',
        '9_10_W_',
    ],
    disp_prime = [
        '2.0_D_',
        '4.0_D_',
        '6.0_D_',
        '8.0_D_',
    ],
    disp_prep = [
        '2.0b_D_',
        '4.0b_D_',
        '6.0b_D_',
        '8.0b_D_',
    ],
    disp_main = [
        '2.1_D_',
        '4.1_D_',
        '6.1_D_',
        '8.1_D_',
    ],
)

utils.serializer.register(globals())

dir_list_url: str = 'http://10.10.0.56:5050/dir_list'
# dir_list_url: str = 'http://localhost:5050/dir_list'

class PathInfo(TypedDict):
    '''
    Info about a path:

    posix-style path relative to protocol root
    last modified timestamp in isoformat
    sha256 hexdigest

    example:

    {
      "path": "automation_v5.0/7_W_3X_beforeStains_leaves10ul_PBS.LHC",
      "modified": "2022-02-15 10:57:50",
      "sha256": "cf9eaf0e9a4cbaacba35433ae811f9a657b9a3ddc2ddca0b72d1ace3397259a2"
    }
    '''
    path: str
    modified: str
    sha256: str

class Response(TypedDict):
    value: list[PathInfo]

def get_protocol_paths() -> dict[str, ProtocolPaths]:
    return utils.serializer.read_json('protocol_paths.json')

def paths_v5():
    return get_protocol_paths()['automation_v5.0']

def update_protocol_dir(protocol_dir: str):
    res: Response = curl(dir_list_url)
    protocol_paths = make_protocol_paths(protocol_dir, res['value'])
    all_protocol_paths = get_protocol_paths()
    all_protocol_paths[protocol_dir] = protocol_paths
    utils.serializer.write_json(all_protocol_paths, 'protocol_paths.json', indent=2)

def make_protocol_paths(protocol_dir: str, infos: list[PathInfo]):
    protocol_dir = protocol_dir.rstrip('/')

    lhcs: list[str] = []
    for info in infos:
        dir, _, lhc = info['path'].partition('/')
        if dir == protocol_dir:
            lhcs += [lhc]

    def resolve_one(prefix: str) -> str:
        candidates = [
            protocol_dir + '/' + lhc
            for lhc in lhcs
            if lhc.startswith(prefix)
        ]
        if len(candidates) > 1:
            raise ValueError(f'More than one candidate for {prefix=}: {candidates}')
        elif candidates:
            return candidates[0]
        else:
            return ''

    def resolve(prefixes: list[str]) -> list[str]:
        return [resolve_one(prefix) for prefix in prefixes]

    paths = ProtocolPaths(
        **{
            k: resolve(v)
            for k, v in asdict(template_protocol_paths).items()
        }
    )
    return paths
