from __future__ import annotations
from typing import *
import typing

import argparse

from dataclasses import *

def doc_header(f: Any):
    if isinstance(f, str):
        s = f
    else:
        s = f.__doc__
        assert isinstance(s, str | None)
    if s:
        return s.strip().splitlines()[0]
    else:
        return ''

A = TypeVar('A')

@dataclass(frozen=True)
class option:
    name: str
    value: Any
    help: str = ''

@dataclass(frozen=True)
class Nothing:
    pass

nothing = Nothing()

@dataclass(frozen=True)
class Arg:
    '''
    Decorate a dataclass like so:

        @dataclass(frozen=True)
        class Args:
            flurb: str = arg(default='Flurb2000', help='Specify the flurb')

    You can now parse into the dataclass with:

        args: Args
        parser: argparse.ArgumentParser
        args, parser = arg.parse_args(Args, description='A program for flurbing.')

    The parser is useful to print the help text:

        parser.print_help()
    '''
    helps: dict[Any, str] = field(default_factory=dict)
    enums: dict[Any, list[option]] = field(default_factory=dict)
    def __call__(self, default: A | Nothing = nothing, help: str | Callable[..., Any] | None = None, enum: list[option] | None = None) -> A:
        f: Field[A]
        def default_factory():
            # at this point we know f.type
            if default == nothing:
                f_type: str = f.type # type: ignore
                return eval(f_type)()
            else:
                return default
        f = field(default_factory=default_factory) # type: ignore
        if callable(help):
            help = help.__doc__
        if help:
            self.helps[f] = doc_header(help)
        if enum:
            self.enums[f] = enum
        return f # type: ignore

    def parse_args(self, as_type: Type[A], args: None | list[str] = None, **kws: Any) -> tuple[A, argparse.ArgumentParser]:
        parser = argparse.ArgumentParser(**kws)
        for f in fields(as_type):
            enum = self.enums.get(f)
            name = '--' + f.name.replace('_', '-')
            assert callable(f.default_factory)
            default = f.default_factory()
            if enum:
                parser.add_argument(name, default=default, help=argparse.SUPPRESS)
                for opt in enum:
                    opt_name = '--' + opt.name.replace('_', '-')
                    parser.add_argument(opt_name, dest=f.name, action="store_const", const=opt.value, help=opt.help)
            else:
                f_type = eval(f.type)
                if f_type == list or typing.get_origin(f_type) == list:
                    parser.add_argument(dest=f.name, default=default, nargs="*", help=self.helps.get(f))
                elif f_type == bool:
                    action = 'store_false' if default else 'store_true'
                    parser.add_argument(name, default=bool(default), action=action, help=self.helps.get(f))
                else:
                    parser.add_argument(name, default=default, metavar='X', type=f_type, help=self.helps.get(f))
        v, unknown = parser.parse_known_args(args)
        if unknown:
            raise ValueError('Unknown args: ' + '\n'.join(unknown))
        return as_type(**v.__dict__), parser

arg = Arg()
