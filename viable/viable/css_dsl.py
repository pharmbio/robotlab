from __future__ import annotations
from dataclasses import *
from typing import *

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

@dataclass(frozen=True, slots=True)
class CssEntry:
    property: str
    value: str
    selector: str = '&'

    @classmethod
    def literal(cls, s: str, selector: str = '&'):
        return cls('', s, selector)

    def is_literal(self):
        return self.property == ''

    def css(self):
        if self.is_literal():
            return self.value
        else:
            return self.property + ':' + self.value

    def instantiate(self, attr_name: str, body: str):
        head = self.selector.replace('&', f'[{attr_name}]')
        return head + '{' + body + '}'

    def nest(self, selector: str) -> CssEntry:
        return CssEntry(self.property, self.value, self.selector.replace('&', selector))

A, B = TypeVar('A'), TypeVar('B')
def group_by(xs: Iterable[A], key: Callable[[A], B]) -> dict[B, list[A]]:
    d: dict[B, list[A]] = DefaultDict(list)
    for x in xs:
        d[key(x)] += [x]
    return d

@dataclass(frozen=True, slots=True)
class Css:
    entries: list[CssEntry] = field(default_factory=list)
    is_style: bool = False

    def get_style(self) -> str:
        if self.is_style:
            for entry in self.entries:
                if entry.selector != '&':
                    raise ValueError(f'Cannot transform {entry} to style attribute')
            return ';'.join(entry.css() for entry in self.entries)
        else:
            return ''

    def get_entries(self) -> list[CssEntry]:
        if self.is_style:
            return []
        else:
            return self.entries

    def instantiate(self, attr_name: str):
        for selector, entries in group_by(self.entries, lambda entry: entry.selector).items():
            head = selector.replace('&', f'[{attr_name}]')
            body = ';'.join(entry.css() for entry in entries)
            yield head + '{' + body + '}'

    def __call__(self, literal: str = '', **kwargs: int | str | None) -> Css:
        new_entries: list[CssEntry] = []
        if literal:
            new_entries += [CssEntry.literal(literal)]
        for k, v in kwargs.items():
            if v is None:
                continue
            if isinstance(v, int):
                v = f'{v}px'
            else:
                v = str(v)
            if ks := aliases.get(k):
                for ka in ks:
                    new_entries += [CssEntry(ka, v)]
            else:
                k = k.replace('_', '-')
                new_entries += [CssEntry(k, v)]
        return Css(self.entries + new_entries, is_style=self.is_style)

    add = __call__

    def nest(self, children: dict[str, Css]) -> Css:
        new_entries: list[CssEntry] = []
        for selector, child in children.items():
            new_entries += [entry.nest(selector) for entry in child.entries]
        return Css(self.entries + new_entries, is_style=False)

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
        place_items:      None | str = None,
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
            place_items           = place_items,
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
