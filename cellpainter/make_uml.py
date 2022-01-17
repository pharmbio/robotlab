from typing import Any
from types import ModuleType
from dataclasses import is_dataclass
import inspect
import abc
import os
import re
import sys
import textwrap

from . import analyze_log   # type: ignore

def visualize_modules(out_path: str='cellpainter.dot'):
    my_dir = os.path.dirname(__file__)
    ms: list[ModuleType] = []
    for m in sys.modules.values():
        path = getattr(m, '__file__', None)
        if path and path.startswith(my_dir):
            ms += [m]
    dcs: set[Any] = set()
    abcs: set[Any] = set()
    fns: set[Any] = set()
    cls: set[Any] = set()
    boring = '''
        Program
        Robotarm
        Serializer
        test
        OptimalResult
        nothing
        Plate
        Keep
        Color
        Args
        Ids
        Mutable
        Interleaving
        Arg
        option
        ProtocolArgs
        Nothing
        ProtocolConfig

        Timelike
        SimulatedTime
        WallTime
        ThreadData
    '''.split()
    for m in ms:
        for k, v in m.__dict__.items():
            if k in boring:
                continue
            if inspect.isclass(v):
                if is_dataclass(v):
                    dcs.add(v)
                elif abc.ABC in v.mro():
                    abcs.add(v)
                else:
                    cls.add(v)
            if inspect.isfunction(v) or inspect.isgeneratorfunction(v):
                fns.add(v)
    if 0:
        for s in [dcs, fns, cls, abcs]:
            for x in list(s):
                try:
                    if not inspect.getfile(x).startswith(my_dir):
                        s.remove(x)
                except TypeError:
                    s.remove(x)
        for c in dcs | cls | abcs:
            for k, v in c.__dict__.items():
                if k.startswith('__'):
                    continue
                if k == '_abc_impl':
                    continue
                if inspect.isfunction(v):
                    fns.add(v)
        for c in fns:
            sig = inspect.signature(c)
            if sig:
                print('def', c.__name__ + str(sig).replace("'", ''))
                # hmm includes defaults too
    labels: list[str] = []
    edges: list[str] = []
    dc_names: set[str] = set()
    abc_names: set[str] = set()
    nl = '\n'
    for dc in dcs:
        name = dc.__name__
        dc_names.add(name)
    for bc in abcs:
        name = bc.__name__
        abc_names.add(name)
    # list_abcs: dict[str, str] = {}
    # for c in cls:
    #     for s in getattr(c, '__orig_bases__', []):
    #         con, args = typing.get_origin(s), typing.get_args(s)
    #         if con == list:
    #             list_abcs[c.__name__] = args[0].__name__
    for dc in sorted(dcs | abcs, key=lambda x: x.__name__):
        name = dc.__name__
        fields = inspect.get_annotations(dc)
        super: str | None = None
        for c in dc.mro()[1:]:
            if c in abcs:
                super = c.__name__
                break
        if super:
            trs = [f'''
                <TD WIDTH="350" PORT="class">class {name}({super}):</TD>
            ''']
            edges += [f'''
                {super}:e -> {name}:class:w [arrowhead=empty style=dashed weight=2]
            ''']
        elif fields:
            trs = [f'''
                <TD WIDTH="350" PORT="class">class {name}:</TD>
            ''']
        else:
            trs = [f'''
                <TD WIDTH="200" PORT="class">class {name}</TD>
            ''']
        for k, v in fields.items():
            if k == 'cmd' and v == 'Any | None':
                v = 'Command | None'
            v = v.replace('MoveList', 'list[Move]')
            trs += [f'''
                <TD ALIGN="LEFT" PORT="{k}">{k}: {textwrap.fill(v, width=35).replace(nl, '<BR/>')}</TD>
            ''']
        trs = [f'''
                <TR>{tr.strip()}</TR>''' for tr in trs]
        labels += [f'''{name} [label=<
            <TABLE CELLPADDING="2" FIXEDSIZE="FALSE" BORDER="0" CELLBORDER="1" CELLSPACING="0">{nl.join(trs)}
            </TABLE>
        >]''']
        for k, v in fields.items():
            if k == 'cmd' and v == 'Any | None':
                v = 'Command | None'
            v = v.replace('MoveList', 'list[Move]')
            words = re.findall(r'\b\w+\b', v)
            for other in dc_names | abc_names:
                if other == super:
                    continue
                if other in words:
                    edges += [f'''
                        {name}:{k} -> {other}:class
                    ''']
    out = [*labels, *edges]
    s = nl.join(out).replace('\n\n', '\n')
    dot = '''
    digraph {
        # graph [bgcolor="#2d2d2d"]
        # node [color="#d3d0c8" fontcolor="#d3d0c8"]
        # edge [color="#d3d0c8" fontcolor="#d3d0c8"]
        margin=1.3
        layout=dot
        rankdir=LR
        ranksep=0.8
        nodesep=0.4
        edge [arrowhead=vee arrowsize=1.0]
        node [fontname="Roboto" fontsize=20]
        node [shape=plaintext]
    ''' + s + '''
        RobotarmCmd -> TaggedMoveList [style=invis]
        RobotarmCmd -> MoveListParts [style=invis]
        RobotarmCmd:program_name -> Effect:class [style=dotted, arrowhead=none]
        RobotarmCmd:program_name -> Move:class [style=dotted, arrowhead=none]
    }
    '''
    with open(out_path, 'w') as fp:
        print(dot,  file=fp)

