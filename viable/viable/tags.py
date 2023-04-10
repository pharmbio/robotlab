from __future__ import annotations
from dataclasses import *
from typing import *
import typing_extensions as tx

import abc

def make_aliases():
    aliases=dict(
        w='width'.split(),
        h='height'.split(),
        z='z-index'.split(),
        c='color'.split(),
        bg='background-color'.split(),
    )
    for box in 'border padding margin outline'.split():
        b = box[0]
        aliases |= {
            f'{b}': f'{box}'.split(),
            f'{b}x': f'{box}-left {box}-right'.split(),
            f'{b}y': f'{box}-top {box}-bottom'.split(),
            f'{b}l': f'{box}-left'.split(),
            f'{b}r': f'{box}-right'.split(),
            f'{b}t': f'{box}-top'.split(),
            f'{b}d': f'{box}-down'.split(),
        }
    return aliases

aliases = make_aliases()

@dataclass(frozen=True)
class Css:
    literal: str = ''
    values: dict[str, str] = field(default_factory=dict)
    nested: dict[str, Css] = field(default_factory=dict)
    is_style: bool = False

    def to_css_parts(self, name: str = '&', tidy: bool = True) -> Iterator[tuple[str, str]]:
        literal = [self.literal] if self.literal else []
        items = literal + [f'{k}:{v}' for k, v in self.values.items()]
        if items:
            if tidy:
                yield name, '\n'.join(f'  {item};' for item in items)
            else:
                yield name, ';'.join(items)
        for selector, child in self.nested.items():
            yield from child.to_css_parts(selector.replace('&', name), tidy=tidy)

    def __call__(self, literal: str = '', **kwargs: int | str | None) -> Css:
        values = {}
        for k, v in kwargs.items():
            if v is None:
                continue
            if isinstance(v, int):
                v = f'{v}px'
            else:
                v = str(v)
            if ks := aliases.get(k):
                for ka in ks:
                    values[ka] = v
            else:
                k = k.replace('_', '-')
                values[k] = v
        return self.merge(Css(literal, values, is_style=True))

    add = __call__

    def nest(self, children: dict[str, Css]) -> Css:
        return self.merge(Css('', {}, children))

    def merge(self, other: Css) -> Css:
        '''other-biased merge'''
        values = {
            **self.values,
            **other.values,
        }
        nested = {
            k: self.nested.get(k, Css()).merge(other.nested.get(k, Css()))
            for k in {*self.nested.keys(), *other.nested.keys()}
        }
        return Css(
            self.literal + other.literal,
            values,
            nested,
            self.is_style and other.is_style and not nested
        )

    def grid(
        self,
        template_columns: None | str = None,
        template_rows:    None | str = None,
        template_areas:   None | str = None,
        auto_rows:        None | str = None,
        auto_columns:     None | str = None,
        auto_flow:        None | Literal['row', 'column', 'dense', 'row dense', 'column dense'] = None,
        row_gap:          None | str | int = None,
        column_gap:       None | str | int = None,
        gap:              None | str | int = None,
        justify_items:    None | Literal['start', 'end', 'center', 'stretch', 'baseline'] = None,
        align_items:      None | Literal['start', 'end', 'center', 'stretch', 'baseline'] = None,
        justify_content:  None | Literal['start', 'end', 'center', 'stretch', 'space-between', 'space-around', 'space-evenly'] = None,
        align_content:    None | Literal['start', 'end', 'center', 'stretch', 'space-between', 'space-around', 'space-evenly'] = None,
    ) -> 'Css':
        '''
        sets display: grid and some other common values

        'grid-template-rows', 'grid-template-columns'
        Defines the line names and track sizing functions of the grid columns and rows.

        Examples: '100px minmax(100px, 1fr)' or 'repeat(auto-fit, 100px)'

        'grid-template-areas'
        Defines a grid template by referencing the names of the grid areas which are specified with the grid-area property.

        Examples:
        '. header header header .'
        'sidebar main main main sidebar'
        '. footer footer footer .'

        'grid-auto-rows', 'grid-auto-columns'
        Defines the size of any implicitly-created columns and rows in the grid.

        Examples: '100px' or 'minmax(100px, auto)'

        'grid-auto-flow'
        Controls how auto-placed items are placed in the grid.

        Examples: 'row', 'column', 'dense', 'row dense', or 'column dense'

        'grid-row-gap', 'grid-column-gap', 'grid-gap'
        Defines the size of the gap in the grid.

        Examples: '20px' or '1em 0'

        'justify-items'
        Aligns grid items along the inline (row) axis.
        'align-items'
        Aligns grid items along the block (column) axis.

        Examples: 'start', 'end', 'center', 'stretch', or 'baseline'

        'justify-content'
        Aligns grid items along the inline (row) axis when there is extra space in the grid container.
        'align-content'
        Aligns grid items along the block (column) axis when there is extra space in the grid container.

        Examples: 'start', 'end', 'center', 'stretch', 'space-around', or 'space-between'

        '''
        return self(
            display               = 'grid',
            grid_template_columns = template_columns,
            grid_template_rows    = template_rows,
            grid_template_areas   = template_areas,
            grid_auto_rows        = auto_rows,
            grid_auto_columns     = auto_columns,
            grid_auto_flow        = auto_flow,
            grid_row_gap          = row_gap,
            grid_column_gap       = column_gap,
            grid_gap              = gap,
            justify_items         = justify_items,
            align_items           = align_items,
            justify_content       = justify_content,
            align_content         = align_content,
        )

    def item(
        self,
        row:          str | int | None = None,
        column:       str | int | None = None,
        area:         str | None = None,
        justify_self: Literal['start', 'end', 'center', 'stretch', 'baseline'] | None = None,
        align_self:   Literal['start', 'end', 'center', 'stretch', 'baseline'] | None = None,
        place_self:   Literal['auto', 'start', 'end', 'center', 'stretch'] | None = None,
    ) -> Css:
        '''
        Grid Item Properties
        '''
        if row and column and area is None:
            area = f'{row} / {column}'
            row = None
            column = None
        return self(
            grid_area=area,
            grid_row=str(row) if isinstance(row, int) else row,
            grid_column=str(column) if isinstance(column, int) else column,
            justify_self=justify_self,
            align_self=align_self,
            place_self=place_self,
        )

    def text(
        self,
        family:         str | None = None,
        size:           str | None = None,
        weight:         str | None = None,
        letter_spacing: str | None = None,
        line_height:    str | None = None,
        decoration:     Literal['none', 'underline', 'overline', 'line-through', 'underline overline', 'underline line-through', 'overline line-through', 'underline overline line-through'] | None = None,
        transform:      Literal['none', 'capitalize', 'uppercase', 'lowercase', 'full-width', 'full-size-kana'] | None = None,
        align:          Literal['left', 'right', 'center', 'justify', 'justify-all', 'start', 'end', 'match-parent'] | None = None,
        overflow:       Literal['clip', 'ellipsis', 'auto', 'hidden', 'scroll'] | None = None,
        word_break:     Literal['normal', 'break-all', 'keep-all', 'break-word'] | None = None
    ) -> Css:
        '''
        Font and text properties.
        '''
        return self(
            font_family     = family,
            font_size       = size,
            font_weight     = weight,
            letter_spacing  = letter_spacing,
            line_height     = line_height,
            text_decoration = decoration,
            text_transform  = transform,
            text_align      = align,
            text_overflow   = overflow,
            word_break      = word_break,
        )

    font = text

    @property
    def pointer(self):
        'cursor: pointer'
        return self(cursor='pointer')

    @property
    def user_select_none(self):
        'user-select: none'
        return self(user_select='none')

    @property
    def translate(self, x: int | str | None = None, y: int | str | None = None):
        def px(v: int | str | None) -> str:
            if v is None:
                return '0'
            elif isinstance(v, int):
                return f'{v}px'
            else:
                return v
        return self(transform=f'translate({px(x)},{px(y)})')

    @property
    def border_box(self):
        return self.nest({'& *,& *::before,& *::after': Css()(box_sizing='border-box')})

css = Css()
style = Css(is_style=True)

AttrValue: TypeAlias = None | bool | str | int

def html_esc(txt: str, __table: dict[int, str] = str.maketrans({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    # "'": "&apos;",
    # '"': "&quot;",
    # '`': "&#96;",
})) -> str:
    return txt.translate(__table)

def attr_esc(txt: str, __table: dict[int, str] = str.maketrans({
    '"': "&quot;",
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
        sep = '' # '\n' # '' if indent == 0 else '\n'
        return sep.join(self.to_strs(indent=indent))

css_props = {
    p.replace('-', '_'): [p]
    for p in '''
        align-content align-items align-self all animation animation-delay
        animation-direction animation-duration animation-fill-mode
        animation-iteration-count animation-name animation-play-state
        animation-timing-function backface-visibility background
        backdrop-filter
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
        outline-width overflow overflow-wrap overflow-x overflow-y
        place-items place-self
        padding
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
    for v, left_right in {'t': 'top', 'b': 'bottom', 'l': 'left', 'r': 'right', 'x': 'left right', 'y': 'top bottom'}.items():
        css_props[m+v] = [margin + '-' + left for left in left_right.split()]
css_props['d'] = ['display']
css_props['bg'] = ['background']

Child = TypeVar('Child', Node, str, Css, dict[str, AttrValue])

class Tag(Node):
    _attributes_ = {'children', 'attrs', 'inline_css', 'inline_Css', 'inline_sheet'}
    def __init__(self, *children: Node | str | Css | dict[str, AttrValue], **attrs: AttrValue):
        self.children: list[Node] = []
        self.attrs: dict[str, AttrValue] = {}
        self.inline_Css: list[Css] = []
        self.inline_css: list[str] = []
        self.inline_sheet: list[str] = []
        self.append(*children)
        self.extend(attrs)

    def add(self, child: Child) -> Child:
        self.append(child)
        return child

    def append(self, *children: Node | str | Css | dict[str, AttrValue], **kws: AttrValue) -> tx.Self:
        for child in children:
            if isinstance(child, Css):
                self.inline_Css += [child]
            elif isinstance(child, dict):
                self.extend(child)
            elif isinstance(child, str):
                self.children += [text(child)]
            else:
                self.children += [child]
        return self

    def extend(self, attrs: dict[str, AttrValue] = {}, **kws: AttrValue) -> tx.Self:
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
                if isinstance(v, int):
                    v = str(v)
                if not isinstance(v, str):
                    raise ValueError(f'attribute {k}={v} not str or int')
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
        return self.__class__.__name__.removesuffix('_tag')

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
                elif isinstance(v, str) and v.isalnum():
                    kvs += [f'{k}={v}']
                else:
                    assert isinstance(v, str)
                    kvs += [f'{k}="{attr_esc(v)}"']
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
        for x in self.inline_Css:
            if x.is_style:
                (_, decls), = list(x.to_css_parts(tidy=False))
                self.extend({'style': decls})
                continue
            fingerprint = '\n'.join(f'{sel} {{{decls}}}' for sel, decls in x.to_css_parts())
            if fingerprint in classes:
                name, _ = classes[fingerprint]
            else:
                name = f'css-{len(classes)}'
                nl = '\n'
                inst = '\n'.join(f'{sel} {{{nl}{decls}{nl}}}' for sel, decls in x.to_css_parts(name=f'[{name}]'))
                classes[fingerprint] = name, inst
            self.extend({name: True})
        for child in self.children:
            if isinstance(child, Tag):
                child.make_classes(classes)
        return classes

class tag(Tag):
    _attributes_ = {*Tag._attributes_, 'name'}
    def __init__(self, name: str, *children: Node | str, **attrs: AttrValue):
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
            self.txt = html_esc(txt)

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
class style_tag(Tag): pass
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

def svg(*children: Node | str, **attrs: AttrValue):
    attrs = {'xmlns': "http://www.w3.org/2000/svg", **attrs}
    return tag('svg', *children, **attrs)

class Tags:
    a          = a
    abbr       = abbr
    address    = address
    area       = area
    article    = article
    aside      = aside
    audio      = audio
    b          = b
    base       = base
    bdi        = bdi
    bdo        = bdo
    blockquote = blockquote
    body       = body
    br         = br
    button     = button
    canvas     = canvas
    caption    = caption
    cite       = cite
    code       = code
    col        = col
    colgroup   = colgroup
    data       = data
    datalist   = datalist
    dd         = dd
    details    = details
    dfn        = dfn
    dialog     = dialog
    div        = div
    dl         = dl
    dt         = dt
    em         = em
    embed      = embed
    fieldset   = fieldset
    figcaption = figcaption
    figure     = figure
    footer     = footer
    form       = form
    h1         = h1
    h2         = h2
    h3         = h3
    h4         = h4
    h5         = h5
    h6         = h6
    head       = head
    header     = header
    hgroup     = hgroup
    hr         = hr
    html       = html
    i          = i
    iframe     = iframe
    img        = img
    input      = input
    ins        = ins
    kbd        = kbd
    label      = label
    legend     = legend
    li         = li
    link       = link
    main       = main
    mark       = mark
    menu       = menu
    meta       = meta
    meter      = meter
    nav        = nav
    noscript   = noscript
    ol         = ol
    optgroup   = optgroup
    option     = option
    output     = output
    p          = p
    param      = param
    picture    = picture
    pre        = pre
    progress   = progress
    q          = q
    rp         = rp
    rt         = rt
    ruby       = ruby
    s          = s
    samp       = samp
    script     = script
    section    = section
    select     = select
    slot       = slot
    small      = small
    source     = source
    span       = span
    strong     = strong
    style      = style_tag
    sub        = sub
    summary    = summary
    sup        = sup
    table      = table
    tbody      = tbody
    td         = td
    template   = template
    textarea   = textarea
    tfoot      = tfoot
    th         = th
    thead      = thead
    title      = title
    tr         = tr
    track      = track
    u          = u
    ul         = ul
    var        = var
    video      = video
    wbr        = wbr
    svg        = svg
