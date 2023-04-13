from __future__ import annotations
from typing import *
from dataclasses import *

from viable import js, Int, Tag, div

from datetime import datetime, timedelta

import math

from ..log import ExperimentMetadata, Log

from .. import commands
from ..commands import *
import pbutils
from ..log import CommandState, Message, VisRow, RuntimeMetadata, countdown

from . import common

@dataclass(frozen=True, kw_only=True)
class AnalyzeResult:
    zero_time: datetime
    t_now: float
    runtime_metadata: RuntimeMetadata
    experiment_metadata: ExperimentMetadata
    program_metadata: ProgramMetadata
    completed: bool
    running_state: list[CommandState]
    progress_texts: dict[int, str]
    resources: list[str | None]
    errors: list[Message]
    world: dict[str, str]
    process_is_alive: bool
    sections: dict[str, float]
    time_end: float
    vis: list[VisRow]

    def has_error(self):
        if self.completed:
            return False
        return not self.process_is_alive or self.errors

    @staticmethod
    def init(m: Log, drop_after: float | None = None) -> AnalyzeResult | None:
        runtime_metadata = m.runtime_metadata()
        if not runtime_metadata:
            return None
        completed = runtime_metadata.completed is not None
        zero_time = runtime_metadata.start_time
        t_now = (datetime.now() - zero_time).total_seconds()

        if completed:
            t_now = m.time_end() + 0.01

        alive = common.process_is_alive(runtime_metadata.pid, runtime_metadata.log_filename)

        if not alive:
            t_now = m.time_end() + 0.01

        errors = m.errors()
        if errors:
            t_now = max([e.t for e in errors], default = m.time_end()) + 1

        if drop_after is not None:
            # completed = False
            t_now = drop_after

        running_state = m.running(t=drop_after)
        world = m.world(t=drop_after)
        sections = m.section_starts_with_endpoints()
        program_metadata = m.program_metadata() or ProgramMetadata()

        progress_texts = {
            state.id: text
            for state in running_state
            if drop_after is None
            if (text := m.progress_text(state.id))
        }

        resources = (
            m.db.get(CommandState)
            .select(CommandState.metadata.thread_resource, distinct=True)
            .order(by=CommandState.metadata.thread_resource)
            .list()
        )


        return AnalyzeResult(
            zero_time=zero_time,
            t_now=t_now,
            completed=completed,
            runtime_metadata=runtime_metadata,
            experiment_metadata=m.experiment_metadata() or ExperimentMetadata(),
            program_metadata=program_metadata,
            running_state=running_state,
            progress_texts=progress_texts,
            resources=resources,
            errors=errors,
            world=world,
            process_is_alive=alive,
            sections=sections,
            time_end=m.time_end(),
            vis=m.vis(t_now if not errors else None),
        )

    def entry_desc_for_hover(self, e: CommandState):
        cmd = e.cmd
        match cmd:
            case BiotekCmd() | BlueCmd():
                if cmd.protocol_path:
                    if cmd.action == 'Validate':
                        return cmd.action + ' ' + cmd.protocol_path
                    else:
                        return cmd.protocol_path
                else:
                    return cmd.action
            case IncuCmd():
                if cmd.incu_loc:
                    return cmd.action + ' ' + cmd.incu_loc
                else:
                    return cmd.action
            case _:
                return str(cmd)

    def entry_desc_for_table(self, e: CommandState):
        res = self.entry_desc_for_table_inner(e)
        if (text := self.progress_texts.get(e.metadata.id)):
            return res + ', ' + text
        else:
            return res

    def entry_desc_for_table_inner(self, e: CommandState):
        cmd = e.cmd
        match cmd:
            case commands.RobotarmCmd():
                return cmd.program_name
            case commands.PFCmd():
                return cmd.program_name
            case BiotekCmd() | BlueCmd():
                if cmd.action == 'TestCommunications':
                    return cmd.action
                else:
                    path = str(cmd.protocol_path)
                    path = path.removeprefix('automation_')
                    path = path.removesuffix('.LHC')
                    path = path.removesuffix('.prog')
                    return path
            case FridgeInsert():
                if cmd.expected_barcode:
                    return f'insert {cmd.expected_barcode} with project: {cmd.project}'
                else:
                    return f'insert with project: {cmd.project}'
            case FridgeEject():
                return f'eject {cmd.plate} with project: {cmd.project}'
            case FridgeCmd():
                return cmd.action
            case SquidAcquire():
                return f'acquire {cmd.plate}'
            case SquidStageCmd():
                return cmd.action
            case IncuCmd():
                if cmd.incu_loc:
                    return cmd.action + ' ' + cmd.incu_loc
                else:
                    return cmd.action
            case commands.WaitForCheckpoint() if cmd.plus_seconds.unwrap() > 0.5:
                return f'sleeping to {self.pp_time_at(e.t)}'
            case commands.WaitForCheckpoint():
                return f'waiting for {cmd.name}'
            case commands.Idle() if e.t0:
                return f'sleeping to {self.pp_time_at(e.t)}'
            case _:
                return str(e.cmd_type)

    def running(self):
        d: dict[str, CommandState | None] = {}
        G = pbutils.group_by(self.running_state, key=lambda e: e.metadata.thread_resource)
        for resource in self.resources:
            es = G.get(resource, [])
            if es:
                d[resource or 'main'] = es[0]
            else:
                d[resource or 'main'] = None
            if len(es) > 2:
                print(f'{len(es)} from {resource=}? ({[e.cmd for e in es]})')

        table: list[dict[str, str | float | int | None]] = []
        for resource, e in d.items():
            table.append({
                'resource':  resource,
                'countdown': (
                    e and (
                        ''
                        if self.progress_texts.get(e.metadata.id)
                        else common.pp_secs(e.countdown(self.t_now))
                    )
                ),
                'desc':      e and self.entry_desc_for_table(e),
                'plate':     e and e.metadata.plate_id,
            })
        return table

    def time_at(self, secs: float):
        return self.zero_time + timedelta(seconds=secs)

    def pp_time_at(self, secs: float):
        return self.time_at(secs).strftime('%H:%M:%S')

    def countdown(self, to: float):
        return countdown(self.t_now, to)

    def pp_countdown(self, to: float, zero: str=''):
        return common.pp_secs(self.countdown(to), zero=zero)

    def pretty_sections(self):
        table: list[dict[str, str | float | int]] = []
        for name, t in self.sections.items():
            section, _, last = name.rpartition(' ')
            if last.isdigit():
                batch = str(int(last) + 1)
            else:
                section = name
                batch = ''
            table.append({
                'batch':     batch,
                'section':   section,
                'countdown': self.pp_countdown(t, zero=''),
                't0':        self.pp_time_at(t),
                # 'length':    common.pp_secs(math.ceil(entries.length()), zero=''),
                'total':     common.pp_secs(math.ceil(self.time_end), zero='') if name == 'end' else '',
            })
        return table

    def make_vis(self, t_end: Int | None = None) -> Tag:
        width = 23

        area = div()
        area.css += f'''
            position: relative;
            user-select: none;
            width: {round(width*(len(self.sections)+1)*2.3, 1)}px;
            transform: translateY(1em);
            height: calc(100% - 1em);
        '''
        area.css += '''
            & > * {
                color: #000;
                position: absolute;
                border-radius: 0px;
                outline: 1px #0005 solid;
                display: grid;
                place-items: center;
                font-size: 14px;
                min-height: 1px;
                background: var(--row-color);
            }
            & > :not(:hover)::before {
                position: absolute;
                left: 0;
                bottom: 0;
                width: 100%;
                height: var(--pct-incomplete);
                content: "";
                background: #0005;
            }
            & > [can-hover]:hover::after {
                font-size: 16px;
                color: #000;
                position: absolute;
                outline: 1px #0005 solid;
                padding: 5px;
                margin: 0;
                border-radius: 0 5px 5px 5px;
                content: var(--info);
                left: calc(100% + 1px);
                opacity: 1.0;
                top: 0;
                background: var(--row-color);
                white-space: pre;
                z-index: 1;
            }
        '''

        max_length = max([
            row.section_t_with_overflow - row.section_t0
            for row in self.vis
        ], default=1.0)

        for row in self.vis:
            slot = 0
            metadata = row.state and row.state.metadata
            if row.state:
                source = row.state.resource or ''
            elif row.bg:
                source = 'bg'
            elif row.now:
                source = 'now'
            else:
                source = ''
            if source == 'disp':
                slot = 1
            my_width = 1
            if source in ('now', 'bg'):
                my_width = 2

            color = {
                'wash': 'var(--cyan)',
                'blue': 'var(--blue)',
                'disp': 'var(--purple)',
                'incu': 'var(--green)',
                'fridge': 'var(--cyan)',
                'squid': 'var(--red)',
                'nikon': 'var(--orange)',
                'now': '#fff',
                'bg': 'var(--bg-bright)',
            }[source]
            can_hover = source not in ('now', 'bg')

            y0 = (row.t0 - row.section_t0) / (max_length or 1.0)
            y1 = (row.t - row.section_t0) / (max_length or 1.0)
            h = y1 - y0

            if row.state and isinstance(row.state.cmd, BiotekCmd | BlueCmd):
                info = row.state.cmd.protocol_path or row.state.cmd.action
            elif row.state and isinstance(row.state.cmd, IncuCmd):
                loc = row.state.cmd.incu_loc
                action = row.state.cmd.action
                if loc:
                    info = f'{action} {loc}'
                else:
                    info = action
            elif row.state and isinstance(row.state.cmd, PhysicalCommand):
                info = str(row.state.cmd)
            else:
                info = ''
            title: dict[str, Any] | div = {}
            row_title = row.section if row.bg else ''
            if row_title and row_title != 'begin':
                title = div(
                    row_title.strip(' 0123456789'),
                    css='''
                        color: var(--fg);
                        position: absolute;
                        left: 50%;
                        top: 0;
                        transform: translate(-50%, -100%);
                        white-space: nowrap;
                        background: unset;
                    '''
                )
            plate_id = metadata and metadata.plate_id or ''
            duration = row.t - row.t0

            frac_complete = (self.t_now - row.t0) / (duration or 1.0)
            if frac_complete > 1:
                frac_complete = 1.0
            if frac_complete < 0:
                frac_complete = 0.0
            if not row.state:
                frac_complete = 1.0

            if row.state and row.state.state == 'planned':
                frac_complete = 0.0

            area += div(
                title,
                plate_id,
                can_hover=can_hover,
                style=f'''
                    left:{(row.section_column*2.3 + slot) * width:.0f}px;
                    top:{  y0 * 100:.3f}%;
                    height:{h * 100:.3f}%;
                    --row-color:{color};
                    --info:{repr(info)};
                    --pct-incomplete:{100 - frac_complete * 100:.3f}%;
                ''',
                css_=f'''
                    width: {width * my_width - 2}px;
                ''',
                css__='cursor: pointer' if t_end is not None else '',
                data_t0=str(row.t0),
                data_t=str(row.t),
            )

        if t_end:
            cmd = js(f'''
                if (!event.buttons) return
                let frac = (event.offsetY - 2) / event.target.clientHeight
                let t = Number(event.target.dataset.t)
                let t0 = Number(event.target.dataset.t0)
                let d = t - t0
                let T = t0 + frac * d
                if (!isFinite(T)) return
                T = Math.round(T)
                {t_end.update(js('T'))}
            ''').iife().fragment
            area.onmousemove += cmd
            area.onmousedown += cmd

        return area

