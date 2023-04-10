from __future__ import annotations
import viable as V
from datetime import date, timedelta
from pbutils import p
import pbutils
from viable import Serve, Flask, call, store, js, div, css, style

from typing import *
from dataclasses import *

serve = Serve(app := Flask(__name__))
serve.suppress_flask_logging()

weeks = [
    [
        date.fromisocalendar(2023, week + 1, day + 1)
        for day in range(7)
    ]
    for week in range(52)
]
G = pbutils.group_by(weeks, lambda w: w[0].month)
flat = {
    # start in April
    col - 3: sum(days, [])
    for col, days in G.items()
    if 3 < col <= 12
} | p

class interesting:
    object_fit = 'object-fit'
    """
    How an element's content should be scaled and cropped.

    Examples: 'contain', 'cover', 'fill', 'none', 'scale-down'
    """

    pointer_events = 'pointer-events'
    """
    Whether an element can be the target of pointer events.

    Examples: 'none', 'auto'
    """

@serve.one()
def index():
    yield css.nest({
        '*': css(m=0),
        'html': css.border_box,
        'html,body': css(h='100%'),
        'body': css(p=5).font(family='sans'),
    })
    g = div(css.grid(auto_columns='1fr', gap='0px 12px'))
    for col, days in flat.items():
        g += div(days[0].strftime('%B'), style.item(1, col), css.item(justify_self='center'))
        for i, day in enumerate(days):
            g += div(
                style.item(i+2, col),
                div('M Ti O To F L S'.split()[day.weekday()], css.item(justify_self='center')),
                div(str(day.day)),
                div(str(day.isocalendar().week) if day.weekday() == 0 else '', css.font(weight='bold')),
                css.grid(
                    template_columns='24px 24px 1fr',
                    justify_items='end',
                ),
                css(
                    bg='#f003' if day.weekday() == 6 else None,
                    px=5,
                    mt=-1 if day.weekday() % 7 != 0 else 5,
                    b='1px black solid',
                ),
            )
    yield g
