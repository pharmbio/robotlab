from __future__ import annotations
from typing import Iterable, cast, Any

from .minifier import minify

import abc
import re

def esc(txt: str, __table: dict[int, str] = str.maketrans({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    "'": "&apos;",
    '"': "&quot;",
    '`': "&#96;",
})) -> str:
    return txt.translate(__table)

def css_esc(txt: str, __table: dict[int, str] = str.maketrans({
    "<": r"\<",
    ">": r"\>",
    "&": r"\&",
    "'": r"\'",
    '"': r"\❞",
    '\\': "\\\\",
})) -> str:
    return txt.translate(__table)

class IAddable:
    def __init__(self):
        self.value = None

    def __iadd__(self, value: str):
        self.value = value
        return self

class Node(abc.ABC):
    @abc.abstractmethod
    def to_strs(self, *, indent: int=0, i: int=0) -> Iterable[str]:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.to_str()

    def to_str(self, indent: int=2) -> str:
        sep = '' if indent == 0 else '\n'
        return sep.join(self.to_strs(indent=indent))

css_props = {
    p.replace('-', '_'): [p]
    for p in '''
        align-content align-items align-self all animation animation-delay
        animation-direction animation-duration animation-fill-mode
        animation-iteration-count animation-name animation-play-state
        animation-timing-function backface-visibility background
        background-attachment background-blend-mode background-clip
        background-color background-image background-origin
        background-position background-repeat background-size border
        border-bottom border-bottom-color border-bottom-left-radius
        border-bottom-right-radius border-bottom-style border-bottom-width
        border-collapse border-color border-image border-image-outset
        border-image-repeat border-image-slice border-image-source
        border-image-width border-left border-left-color border-left-style
        border-left-width border-radius border-right border-right-color
        border-right-style border-right-width border-spacing
        border-style border-top border-top-color border-top-left-radius
        border-top-right-radius border-top-style border-top-width border-width
        bottom box-decoration-break box-shadow box-sizing break-after
        break-before break-inside caption-side caret-color clear clip
        clip-path color column-count column-fill column-gap column-rule
        column-rule-color column-rule-style column-rule-width column-span
        column-width columns content counter-increment counter-reset cursor
        direction display empty-cells filter flex flex-basis flex-direction
        flex-flow flex-grow flex-shrink flex-wrap float font font-family
        font-feature-settings font-kerning font-size font-size-adjust
        font-stretch font-style font-variant font-variant-caps font-weight
        gap grid grid-area grid-auto-columns grid-auto-flow grid-auto-rows
        grid-column grid-column-end grid-column-gap grid-column-start grid-gap
        grid-row grid-row-end grid-row-gap grid-row-start grid-template
        grid-template-areas grid-template-columns grid-template-rows
        hanging-punctuation height hyphens image-rendering isolation
        justify-content justify-self left letter-spacing line-height
        list-style list-style-image list-style-position list-style-type margin
        margin-bottom margin-left margin-right margin-top max-height max-width
        min-height min-width mix-blend-mode object-fit object-position opacity
        order orphans outline outline-color outline-offset outline-style
        outline-width overflow overflow-wrap overflow-x overflow-y padding
        padding-bottom padding-left padding-right padding-top page-break-after
        page-break-before page-break-inside perspective perspective-origin
        pointer-events position quotes resize right row-gap scroll-behavior
        tab-size table-layout text-align text-align-last text-decoration
        text-decoration-color text-decoration-line text-decoration-style
        text-indent text-justify text-overflow text-shadow text-transform top
        transform transform-origin transform-style transition transition-delay
        transition-duration transition-property transition-timing-function
        unicode-bidi user-select vertical-align visibility white-space widows
        width word-break word-spacing word-wrap writing-mode z-index
    '''.split()
}
for m, margin in {'m': 'margin', 'p': 'padding', 'b': 'border'}.items():
    css_props[m] = [margin]
    for x, left_right in {'t': 'top', 'b': 'bottom', 'l': 'left', 'r': 'right', 'x': 'left right', 'y': 'top bottom'}.items():
        css_props[m+x] = [margin + '-' + left for left in left_right.split()]
css_props['d'] = ['display']
css_props['bg'] = ['background']

class Tag(Node):
    _attributes_ = {'children', 'attrs', 'inline_css', 'inline_sheet'}
    def __init__(self, *children: Node | str | dict[str, str | bool | None], **attrs: str | bool | None):
        self.children: list[Node] = []
        self.attrs: dict[str, str | bool | None] = {}
        self.inline_css: list[str] = []
        self.inline_sheet: list[str] = []
        self.append(*children)
        self.extend(attrs)

    def append(self, *children: Node | str | dict[str, str | bool | None], **kws: str | bool | None) -> Tag:
        self.children += [
            text(child) if isinstance(child, str) else child
            for child in children
            if not isinstance(child, dict)
        ]
        for child in children:
            if isinstance(child, dict):
                self.extend(child)
        self.extend(kws)
        return self

    def extend(self, attrs: dict[str, str | bool | None] = {}, **kws: str | bool | None) -> Tag:
        for k, v in {**attrs, **kws}.items():
            k = k.strip('_')
            if k == 'css':
                assert isinstance(v, str), 'inline css must be str'
                self.inline_css += [v]
                continue
            if k == 'sheet':
                assert isinstance(v, str), 'inline css must be str'
                self.inline_sheet += [v]
                continue
            if props := css_props.get(k):
                v = cast(Any, v)
                if isinstance(v, int):
                    if v == 0:
                        v = '0'
                    else:
                        v = str(v) + 'px'
                assert isinstance(v, str)
                vs: list[str] = []
                for prop in props:
                    vs += [f'{prop}:{v}']
                v = ';'.join(vs)
                k = 'style'
            else:
                k = k.replace('_', '-')
            if k == 'className':
                k = 'class'
            if k == 'htmlFor':
                k = 'for'
            if k in self.attrs:
                if k == 'style':
                    sep = ';'
                elif k.startswith('on'):
                    sep = ';'
                elif k == 'class':
                    sep = ' '
                else:
                    raise ValueError(f'only event handlers, styles and classes can be combined, not {k}')
                if not isinstance(v, str):
                    raise ValueError(f'attribute {k}={v} not str' )
                self.attrs[k] = str(self.attrs[k]).rstrip(sep) + sep + v.lstrip(sep)
            else:
                self.attrs[k] = v
        return self

    def __iadd__(self, other: str | Tag) -> Tag:
        return self.append(other)

    def __getattr__(self, attr: str) -> IAddable:
        if attr in self._attributes_:
            return self.__dict__[attr]
        return IAddable()

    def __setattr__(self, attr: str, value: IAddable):
        if attr in self._attributes_:
            self.__dict__[attr] = value
        else:
            assert isinstance(value, IAddable)
            self.extend({attr: value.value})

    def tag_name(self) -> str:
        return self.__class__.__name__

    def to_strs(self, *, indent: int=2, i: int=0) -> Iterable[str]:
        if self.attrs:
            kvs: list[str] = []
            for k, v in sorted(self.attrs.items()):
                if v is False:
                    continue
                elif v is None:
                    continue
                elif v is True:
                    kvs += [k]
                else:
                    assert isinstance(v, str)
                    if k.startswith('on'):
                        v = minify(v)
                    if re.match(r'[\w\-\.,:;/+@#?(){}[\]]+$', v):
                        # https://html.spec.whatwg.org/multipage/syntax.html#unquoted
                        kvs += [f'{k}={v}']
                    elif re.match(r'[\s<>=`\w\-\.,:;/+@#?(){}[\]"]+$', v):
                        kvs += [f"{k}='{v}'"]
                    else:
                        kvs += [f'{k}="{esc(v)}"']
            attrs = ' ' + ' '.join(kvs)
        else:
            attrs = ''
        name = self.tag_name()
        close = f'</{name}>'
        if name in (
            # https://html.spec.whatwg.org/multipage/syntax.html#void-elements
            'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'source', 'track', 'wbr',
        ):
            close = ''
        if len(self.children) == 0:
            yield ' ' * i + f'<{name}{attrs}>{close}'
        elif len(self.children) == 1 and isinstance(self.children[0], text):
            yield ' ' * i + f'<{name}{attrs}>{self.children[0].to_str()}{close}'
        else:
            yield ' ' * i + f'<{name}{attrs}>'
            for child in self.children:
                if child:
                    yield from child.to_strs(indent=indent, i=i+indent)
            yield ' ' * i + close

    def make_classes(self, classes: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
        for decls in self.inline_sheet:
            if decls not in classes:
                classes[decls] = '', decls
        self.inline_sheet.clear()
        for decls in self.inline_css:
            if decls in classes:
                name, _ = classes[decls]
            else:
                name = f'css-{len(classes)}'
                if '-&' in decls:
                    decls = decls.replace('-&', f'-{name}')
                if '&' in decls:
                    inst = decls.replace('&', f'[{name}]')
                else:
                    inst = f'[{name}] {{{decls}}}'
                classes[decls] = name, inst
            self.extend({name: True})
        self.inline_css.clear()
        for child in self.children:
            if isinstance(child, Tag):
                child.make_classes(classes)
        return classes

class tag(Tag):
    _attributes_ = {*Tag._attributes_, 'name'}
    def __init__(self, name: str, *children: Node | str, **attrs: str | int | bool | None | float):
        super(tag, self).__init__(*children, **attrs)
        self.name = name

    def tag_name(self) -> str:
        return self.name

class text(Node):
    def __init__(self, txt: str, raw: bool=False):
        super(text, self).__init__()
        self.raw = raw
        if raw:
            self.txt = txt
        else:
            self.txt = esc(txt)

    def tag_name(self) -> str:
        return ''

    def to_strs(self, *, indent: int=0, i: int=0) -> Iterable[str]:
        if self.raw:
            yield self.txt
        else:
            yield ' ' * i + self.txt

def raw(txt: str) -> text:
    return text(txt, raw=True)

class a(Tag): pass
class abbr(Tag): pass
class address(Tag): pass
class area(Tag): pass
class article(Tag): pass
class aside(Tag): pass
class audio(Tag): pass
class b(Tag): pass
class base(Tag): pass
class bdi(Tag): pass
class bdo(Tag): pass
class blockquote(Tag): pass
class body(Tag): pass
class br(Tag): pass
class button(Tag): pass
class canvas(Tag): pass
class caption(Tag): pass
class cite(Tag): pass
class code(Tag): pass
class col(Tag): pass
class colgroup(Tag): pass
class data(Tag): pass
class datalist(Tag): pass
class dd(Tag): pass
# class del(Tag): pass
class details(Tag): pass
class dfn(Tag): pass
class dialog(Tag): pass
class div(Tag): pass
class dl(Tag): pass
class dt(Tag): pass
class em(Tag): pass
class embed(Tag): pass
class fieldset(Tag): pass
class figcaption(Tag): pass
class figure(Tag): pass
class footer(Tag): pass
class form(Tag): pass
class h1(Tag): pass
class h2(Tag): pass
class h3(Tag): pass
class h4(Tag): pass
class h5(Tag): pass
class h6(Tag): pass
class head(Tag): pass
class header(Tag): pass
class hgroup(Tag): pass
class hr(Tag): pass
class html(Tag): pass
class i(Tag): pass
class iframe(Tag): pass
class img(Tag): pass
class input(Tag): pass
class ins(Tag): pass
class kbd(Tag): pass
class label(Tag): pass
class legend(Tag): pass
class li(Tag): pass
class link(Tag): pass
class main(Tag): pass
# class map(Tag): pass
class mark(Tag): pass
class menu(Tag): pass
class meta(Tag): pass
class meter(Tag): pass
class nav(Tag): pass
class noscript(Tag): pass
# class object(Tag): pass
class ol(Tag): pass
class optgroup(Tag): pass
class option(Tag): pass
class output(Tag): pass
class p(Tag): pass
class param(Tag): pass
class picture(Tag): pass
class pre(Tag): pass
class progress(Tag): pass
class q(Tag): pass
class rp(Tag): pass
class rt(Tag): pass
class ruby(Tag): pass
class s(Tag): pass
class samp(Tag): pass
class script(Tag): pass
class section(Tag): pass
class select(Tag): pass
class slot(Tag): pass
class small(Tag): pass
class source(Tag): pass
class span(Tag): pass
class strong(Tag): pass
class style(Tag): pass
class sub(Tag): pass
class summary(Tag): pass
class sup(Tag): pass
class table(Tag): pass
class tbody(Tag): pass
class td(Tag): pass
class template(Tag): pass
class textarea(Tag): pass
class tfoot(Tag): pass
class th(Tag): pass
class thead(Tag): pass
# class time(Tag): pass
class title(Tag): pass
class tr(Tag): pass
class track(Tag): pass
class u(Tag): pass
class ul(Tag): pass
class var(Tag): pass
class video(Tag): pass
class wbr(Tag): pass
