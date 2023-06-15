from __future__ import annotations
from typing import *
from dataclasses import *

from viable import store, call, Str, Bool, div, button

from .. import protocol_paths
import viable as V
import viable.provenance as Vp

from pathlib import Path
from subprocess import Popen, DEVNULL
import json
import platform
import shlex
import textwrap
import subprocess

from ..cli import Args
from .. import cli

import pbutils
from ..small_protocols import small_protocols_dict, SmallProtocolData
from ..runtime import RuntimeConfig

from . import common

import viable.provenance as Vp
from viable import label, span
from viable.provenance import Int, Str, Bool

from urllib.parse import quote_plus

import labrobots
from labrobots.liconic import FridgeSlots

@dataclass(frozen=True, kw_only=True, order=True)
class Plate:
    project: str
    barcode: str

    def make_name_with_metadata(self, plate_target: PlateTarget):
        if plate_target.metadata:
            return f'{self.barcode}_{self.project}_{plate_target.metadata}'
        else:
            return f'{self.barcode}_{self.project}'

@dataclass(frozen=True, kw_only=True)
class PlateTarget:
    metadata: str | None = None
    squid_protocol: str | None = None

@dataclass(frozen=True)
class ExternalState:
    config: RuntimeConfig

    @pbutils.throttle(1.0)
    def painter_protocol_paths(self):
        if self.config.name == 'live':
            protocol_paths.update_protocol_paths()
        return protocol_paths.get_protocol_paths()

    @pbutils.throttle(1.0)
    def last_barcode(self):
        if self.config.name == 'pf-live':
            return labrobots.WindowsGBG().remote().barcode.read()
        else:
            import random
            return f'PT{random.randint(0, 999999):06}'

    @pbutils.throttle(1.0)
    def fridge_contents_raw_slots(self) -> FridgeSlots:
        if self.config.name == 'pf-live':
            return labrobots.WindowsGBG().remote().fridge.contents()
        else:
            return {
                '1x1': {'project': 'sim', 'plate': 'S01'},
                '1x2': {'project': 'sim', 'plate': 'S03'},
                '1x3': {'project': 'sim', 'plate': 'S02'},
                '1x4': {'project': '', 'plate': ''},
                '1x5': {'project': '', 'plate': ''},
            }

    def fridge_contents(self) -> dict[Plate, str]:
        slots = self.fridge_contents_raw_slots()
        locs = dict[Plate, str]()
        for loc, slot in slots.items():
            locs[Plate(project=slot['project'], barcode=slot['plate'])] = loc

        # sort projects alphabetically,

        by_project = pbutils.group_by(locs.keys(), lambda plate: plate.project)
        plate_order = {plate: i for i, (plate, _target) in enumerate(self.imager_plate_metadata())}
        last_index = len(plate_order)

        out = dict[Plate, str]()
        for _project, plates in sorted(by_project.items()):
            # first sort plates alphabetically, then put plates according to order in metadata file
            for plate in sorted(sorted(plates), key=lambda plate: plate_order.get(plate, last_index)):
                out[plate] = locs[plate]

        return out

    @pbutils.throttle(1.0)
    def squid_protocols(self) -> list[str]:
        if self.config.name == 'pf-live':
            return labrobots.MikroAsus().remote().squid.list_protocols()
        else:
            return '''
                protocols/short_pe.json
                protocols/short_pe2.json
            '''.split()

    @pbutils.throttle(1.0)
    def imager_plate_metadata(self) -> list[tuple[Plate, PlateTarget]]:
        if (dir := self.config.plate_metadata_dir):
            out: list[tuple[Plate, PlateTarget]] = []
            for csv in sorted(Path(dir).glob('**/*csv'), key=lambda path: path.stem):
                for line in csv.read_text().splitlines():
                    match [part.strip() for part in line.split(',')]:
                        case [project, barcode, metadata, *squid_protocol] if project == csv.stem :
                            plate = Plate(project=project, barcode=barcode)
                            target = PlateTarget(
                                metadata = metadata,
                                squid_protocol = squid_protocol[0] if squid_protocol else None,
                            )
                            out += [(plate, target)]
                        case _:
                            pass
            return out
        else:
            return []

    def add_imager_plate_metadata(self):
        if (dir := self.config.plate_metadata_dir):
            fridge = self.fridge_contents()
            metadata = pbutils.group_by(self.imager_plate_metadata(), lambda plate_target: plate_target[0])
            todo = DefaultDict[str, list[Plate]](list)
            for plate in fridge:
                if plate not in metadata:
                    todo[plate.project] += [plate]
            for project, plates in todo.items():
                with open(Path(dir) / f'{project}.csv', 'a') as fp:
                    for plate in plates:
                        assert plate.project == project
                        print(f'{plate.project},{plate.barcode},', file=fp)
            if not todo:
                return 'Nothing to do.'
            else:
                return 'Wrote ' + ', '.join(f'{len(plates)} lines to {project}.csv' for project, plates in todo.items()) + '.'
        else:
            config = self.config
            return f'Plate metadata directory not configured ({config=})'

    def imager_projects(self) -> list[str]:
        '''Project names from fridge and from imager-plate-metadata'''
        out = set[str]()
        for plate, _ in self.imager_plate_metadata():
            out |= {plate.project}
        for plate, _ in self.fridge_contents().items():
            out |= {plate.project}
        return sorted(out)

    def imager_filtered_plate_targets(self, projects: list[str] | set[str]) -> list[tuple[Plate, PlateTarget]]:
        '''Plates with target metadata and squid protocol filtered by some projects'''
        projects = set(projects)
        fridge = self.fridge_contents()
        metadata = pbutils.group_by(self.imager_plate_metadata(), lambda plate_target: plate_target[0])
        for plate in fridge:
            if plate not in metadata:
                metadata[plate] += [(plate, PlateTarget())]
        out: list[tuple[Plate, PlateTarget]] = []
        for _, targets in metadata.items():
            for plate, target in targets:
                if plate.project in projects:
                    out += [(plate, target)]
        return out

def start(args: Args, simulate: bool, config: RuntimeConfig, push_state: bool=True):
    config_name = 'simulate' if simulate else config.name
    log_filename = cli.args_to_filename(replace(args, config_name=config_name))
    args = replace(
        args,
        config_name=config_name,
        log_filename=log_filename,
        force_update_protocol_paths=config.name == 'live',
        yes=True,
    )
    Path('cache').mkdir(exist_ok=True)
    cmd = [
        'sh', '-c',
        '''
            echo starting... >"$2"
            cellpainter --json-arg "$1" 2>>"$2"
        ''',
        '--',
        json.dumps(pbutils.nub(args)),
        common.as_stderr(log_filename),
    ]
    Popen(cmd, start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
    common.path_var_assign(log_filename, push_state=push_state)

form_css = '''
    & {
        display: grid;
        grid-template-columns: auto auto;
        place-items: center;
        grid-gap: 10px;
        margin: 0 auto;
        user-select: none;
    }
    & input {
        border: 1px #0003 solid;
        border-right-color: #fff2;
        border-bottom-color: #fff2;
    }
    & button {
        border-width: 1px;
    }
    & input, & button, & select {
        padding: 8px;
        border-radius: 2px;
        background: var(--bg);
        color: var(--fg);
    }
    & select.two {
        padding: 0;
    }
    & select.two option {
        padding-left: 8px;
    }
    & select {
        width: 100%;
        padding-left: 4px;
    }
    & input:focus-visible, & button:focus-visible, & select:focus-visible {
        outline: 2px  var(--blue) solid;
        outline-color: var(--blue);
    }
    & input:hover {
        border-color: var(--blue);
    }
    & .wide {
        grid-column: 1 / span 2;
    }
    & > button {
        width: 100%;
    }
    & > label {
        display: contents;
        cursor: pointer;
    }
    & > label > span {
        justify-self: right;
    }
    & input, & select {
        width: 300px;
    }
    & > label > span {
        grid-column: 1;
    }
''' + common.inverted_inputs_css

def form(*vs: Int | Str | Bool | Vp.List | None):
    for v in vs:
        if v is None:
            yield div(grid_column='1 / -1')
        elif isinstance(v, Vp.List):
            inp = v.select([
                V.option(x, value=x, selected=x in v.value)
                for x in v.options
            ])
            inp.extend(grid_column='1 / -1', width='100%', height='100%', grid_row='span 10', font_size='91%')
            yield inp
        else:
            inp = v.input()
            inp.extend(id_=v.name, spellcheck="false", autocomplete="off")
            if len(getattr(v, 'options', []) or []) == 2:
                inp.extend(
                    class_='two',
                    size='2',
                    overflow='hidden'
                )
            yield label(
                span(f"{v.name or ''}:"),
                inp,
                title=v.desc,
            )

A = TypeVar('A')

@dataclass(frozen=True)
class LazyIterate(Generic[A]):
    k: Callable[[], Iterable[A]]
    def __iter__(self) -> Generator[A, None, None]:
        # print('__iter__')
        yield from self.k()

    def __len__(self):
        # print('__len__')
        return len(list(self.k()))

def start_form(*, config: RuntimeConfig):

    imager = config.name != 'live'
    painter = config.name != 'pf-live'

    options = {
        **({'cell-paint': 'cell-paint'} if painter else {}),
        **({'squid-from-fridge-v1': 'squid-from-fridge-v1'} if imager else {}),
        # **({'nikon-from-fridge-v1': 'nikon-from-fridge-v1'} if imager else {}),
        # **({'fridge-metadata': 'fridge-metadata'} if imager else {}),
        **({'fridge-contents': 'fridge-contents'} if imager else {}),
        **({'fridge-unload': 'fridge-unload'} if imager else {}),
        # **({'nikon-from-fridge-v1': 'nikon-from-fridge-v1'} if imager else {}),
        **{
            k.replace('_', '-'): v
            for k, v in small_protocols_dict(imager=imager, painter=painter).items()
        }
    }

    protocol = store.str(default=tuple(options.keys())[0], options=tuple(options.keys()))
    store.assign_names(locals())

    external_state = ExternalState(config)

    desc = store.str(name='description', desc='Example: "specs395-v1"')
    operators = store.str(name='operators', desc='Example: "Amelie and Christa"')
    incu = store.str(name='incubation times', default='20:00', desc='The incubation times in seconds or minutes:seconds, separated by comma. If too few values are specified, the last value is repeated. Example: 21:00,20:00')
    batch_sizes = store.str(default='6', name='batch sizes', desc='The number of plates per batch, separated by comma. Example: 6,6')

    protocol_dir = store.str(
        default='automation_v5.0',
        name='protocol dir',
        desc='Directory on the windows computer to read biotek LHC files from',
        options=LazyIterate(lambda: sorted(external_state.painter_protocol_paths().keys())),
    )

    final_washes = store.str(
        name='final wash rounds',
        options=['one', 'two'],
        desc='Number of final wash rounds. Either run 9_W_*.LHC once or run 9_10_W_*.LHC twice.',
    )

    fridge_projects_suggestions = store.str(
        name='project',
        default='',
        suggestions=external_state.imager_projects(),
    )
    squid_protocol = (
        store.str(
            name='squid protocol',
            options=external_state.squid_protocols(),
        ) if 'squid' in protocol.value else
        store.str(
            name='nikon job',
            default='CellPainting_Automation_PE_squid',
            # get nikon protocol names from their sqlite db?
        )
    )

    fridge_RT_time_secs = store.str(name='RT time secs', default='1800')
    store.assign_names(locals())

    selected_fridge_projects = fridge_projects_suggestions.value.split(',')

    name_to_plate = {
        plate.make_name_with_metadata(plate_target): (plate, plate_target)
        for plate, plate_target in external_state.imager_filtered_plate_targets(selected_fridge_projects)
    }

    fridge_plates_for_selected_projects = store.var(
        Vp.List(
            name='squid plates',
            options=(tmp := list(name_to_plate.keys())),
            default=tmp[0:1],
        )
    )
    fridge_plates_for_unload = store.var(
        Vp.List(
            name='squid plates for unload',
            options=(tmp := [
                f'{plate.project}:{plate.barcode}'
                for plate, loc in external_state.fridge_contents().items()
                if loc and plate.project
            ]),
            default=tmp[0:1],
        )
    )
    store.assign_names(locals())

    num_plates = store.str(name='plates', desc='The number of plates')
    params = store.str(name='params', desc=f'Additional parameters to protocol "{protocol.value}"')
    store.assign_names(locals())

    small_data = options.get(protocol.value)

    form_fields: list[Str | Bool | Vp.List | None] = []
    args: Args | None = None
    custom_fields: list[V.Tag] = []

    doc_full = ''
    doc_divs = []

    err: str = ''
    err_full: str = ''

    if protocol.value == 'cell-paint':
        selected_protocol_paths = external_state.painter_protocol_paths().get(protocol_dir.value)

        if selected_protocol_paths and selected_protocol_paths.use_wash():
            two = final_washes
        else:
            two = None

        form_fields = [
            desc,
            operators,
            None,
            batch_sizes,
            incu,
            protocol_dir,
            two,
        ]
        bs = batch_sizes.value
        incu_csv = incu.value
        args = Args(
            protocol='cell-paint',
            batch_sizes=bs,
            incu=incu_csv,
            interleave=True,
            two_final_washes=final_washes.value == 'two',
            lockstep_threshold=10,
            protocol_dir=protocol_dir.value,
            desc=desc.value,
            operators=operators.value,
        )

    elif protocol.value == 'fridge-contents':
        custom_fields = [
            div(
                common.make_table(
                    [
                        dict(asdict(plate), loc=loc)
                        for plate, loc in external_state.fridge_contents().items()
                        if plate.project
                    ]
                ),
                grid_column='1 / -1',
                grid_row='span 10',
                width='100%',
                height='100%',
                z_index='1000',
            ),
            button(
                'add csv stubs to imager-fridge-metadata',
                onclick=call(lambda: common.alert(external_state.add_imager_plate_metadata())),
            )
        ]

    elif protocol.value in 'squid-from-fridge-v1 nikon-from-fridge-v1'.split():
        form_fields = [
            # fridge_project_options,
            fridge_projects_suggestions,
            squid_protocol,
            fridge_RT_time_secs,
            fridge_plates_for_selected_projects,
        ]
        plates: list[str] = []
        for name in fridge_plates_for_selected_projects.value:
            plate, target = name_to_plate[name]
            match target.squid_protocol:
                case None:
                    plates += [f'{squid_protocol.value}:{plate.project}:{plate.barcode}:{name}']
                case target_protocol:
                    plates += [f'{target_protocol     }:{plate.project}:{plate.barcode}:{name}']
        args = Args(
            protocol='squid_from_fridge' if 'squid' in protocol.value else 'nikon_from_fridge',
            params=[
                fridge_RT_time_secs.value,
                *plates,
            ]
        )

    elif protocol.value == 'fridge-unload':
        form_fields = [
            fridge_plates_for_unload
        ]
        args = Args(
            protocol='fridge_unload',
            params=fridge_plates_for_unload.value
        )

    elif isinstance(small_data, SmallProtocolData):
        if 'num_plates' in small_data.args:
            form_fields += [num_plates]
        if small_data.name in ('fridge_put'):
            custom_fields += [
                div(
                    f'Last barcode: {external_state.last_barcode()}',
                    V.css.item(column='span 2'),
                    V.css(user_select='text'),
                ),
                V.queue_refresh(1000),
            ]
            form_fields += [
                params,
                fridge_projects_suggestions,
            ]
            params_value = [
                params.value,
                fridge_projects_suggestions.value,
            ]
        elif small_data.name in ('fridge_load', 'fridge_load_from_top'):
            form_fields += [fridge_projects_suggestions]
            params_value = [fridge_projects_suggestions.value]
        elif 'params' in small_data.args:
            form_fields += [params]
            try:
                params_value = shlex.split(params.value)
            except Exception as e:
                params_value = []
                err = repr(e)
        else:
            params_value = []
        if 'protocol_dir' in small_data.args:
            form_fields += [protocol_dir]
            protocol_dir = protocol_dir.value
        else:
            protocol_dir = protocol_dir.default
        args = Args(
            protocol=small_data.name,
            num_plates=pbutils.catch(lambda: int(num_plates.value), 0),
            params=params_value,
            protocol_dir=protocol_dir,
        )
        doc_full = textwrap.dedent(small_data.make.__doc__ or '').strip()
        doc_header = small_data.doc
        doc_divs = [
            div(
                # fill
                grid_column='1 / span 2',
                grid_row='2 / span 2',
            ),
            div(
                doc_header,
                title=doc_full,
                grid_column='2 / span 1',
                grid_row='2 / span 2',
                css='''
                    max-width: fit-content;
                    padding: 5px 12px;
                    place-self: start;
                ''',
            ),
        ]
    else:
        form_fields = []
        args = None

    if args:
        args = replace(args, initial_fridge_contents_json=json.dumps(external_state.fridge_contents_raw_slots()))

    if args:
        try:
            stages = cli.args_to_stages(
                replace(
                    args,
                    incu='x',
                )
            )
        except BaseException as e:
            err = repr(e)
            import traceback
            err_full = traceback.format_exc()
            stages = []
        if stages:
            start_from_stage = store.str(
                name='start from stage',
                default='start',
                desc='Stage to start from',
                options=stages
            )
            form_fields += [None, start_from_stage]
            if start_from_stage.value:
                args = replace(args, start_from_stage=start_from_stage.value)

    if err:
        args = None


    confirm = ''
    if 'required' in doc_full.lower():
        confirm = doc_full
    if not confirm and args and args.protocol == 'cell-paint':
        if not args.desc:
            confirm += 'Not specified: description.\n'
        if not args.operators:
            confirm += 'Not specified: operators.\n'
        if confirm:
            confirm += '\nStart anyway?'
    yield div(
        *form(protocol),
        *doc_divs,
        *form(*form_fields),
        *custom_fields,
        button(
            'simulate',
            onclick=call(start, args=args, simulate=True, config=config),
            grid_row='-1',
        ) if args else '',
        button(
            common.triangle(), ' ', 'start',
            data_doc=doc_full,
            data_confirm=confirm,
            onclick=
                (
                    'confirm(this.dataset.confirm) && '
                    if confirm
                    else ''
                )
                +
                call(start, args=args, simulate=False, config=config),
            grid_row='-1',
        ) if args else '',
        div(
            V.css(
                b='1px var(--red) solid',
                w='100%',
                h='100%',
                py=5,
                px=5,
                border_radius=2,
                overflow='hidden',
                text_overflow='ellipsis',
            ),
            V.css.grid(),
            div(err, V.css.item(place_self='center'),
                title=f'{err}\n\n{err_full}',
            ),
            grid_column='span 2',
            grid_row='span 2',
        ) if err else '',
        height='100%',
        padding='40px 0',
        grid_area='form',
        user_select='none',
        css_=form_css,
        css='''
            & {
                grid-template-rows: repeat(14, 40px);
                grid-template-columns: 160px 300px;
            }
            & label > span {
                text-align: right;
            }
            & button {
                height: 100%;
            }
        '''
    )

    info = div(
        grid_area='info',
        z_index='1',
        css='''
            & li {
                margin: 8px 0;
            }
            & > div {
                margin: 16px 0;
            }
        '''
    )
    info += running_processes_div()
    vis = '/vis'
    if args:
        vis = '/vis?cmdline=' + quote_plus(cli.args_to_str(args))
    info += div(
        'More:',
        V.ul(
            V.li(V.a('show logs', href='/logs')),
            V.li(V.a('show in visualizer', href=vis)),
            V.li(V.a('edit moves', href='/moves')),
        ),
    )
    yield info
    yield div(
        f'Running on {platform.node()} with config {config.name}',
        grid_area='info-foot',
        opacity='0.85',
        margin='0 auto',
    )

def running_processes_div():
    running_processes: list[tuple[int, str]] = []
    try:
        x = subprocess.check_output(['pgrep', '^cellpainter$']).decode()
    except:
        x = ''
    for pid in x.strip().split('\n'):
        try:
            pid = int(pid)
            process_args = common.get_json_arg_from_argv(pid)
            if isinstance(v := process_args.get("log_filename"), str):
                running_processes += [(pid, v)]
        except:
            pass

    if running_processes:
        ul = V.ul()
        for pid, arg in running_processes:
            ul += V.li(
                V.span(
                    arg,
                    onclick=call(common.path_var_assign, arg),
                    text_decoration='underline',
                    cursor='pointer'
                ),
                V.button(
                    'kill',
                    data_arg=arg,
                    onclick=
                        'window.confirm("Really kill " + this.dataset.arg + "?") && ' +
                        call(common.sigkill, pid),
                    py=5, mx=8, my=0,
                    border_radius=3,
                    border_width=1,
                    border_color='var(--red)',
                ),
            )
        return div('Running processes:', ul)
    else:
        return div()
