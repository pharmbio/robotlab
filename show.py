
from pprint import pformat

def oneof(x, *types):
    return any(isinstance(x, t) for t in types)

def primlike(x):
    is_container = oneof(x, tuple, list, set)
    if is_container:
        return all(map(primlike, x))
    else:
        return oneof(x, int, float, bool, type(None), str, bytes)

def show(x, show_key=str, width=80):

    def go(dent, pre, x, post):
        '''
        only yield (dent +) pre once,
        then yield indent for each subsequent line
        finally yield (dent/indent +) post
        '''
        indent = '  ' + dent
        is_tuple = isinstance(x, tuple)
        is_list = isinstance(x, list)
        is_set = isinstance(x, set)
        if (is_tuple or is_list or is_set) and not primlike(x):
            if is_list:
                begin, end = '[]'
            elif is_tuple:
                begin, end = '()'
            elif is_set:
                begin, end = '{}'
            if len(x) == 0:
                yield dent + pre + begin + end + post
            else:
                yield dent + pre + begin
                for v in x:
                    yield from go(indent, '', v, ',')
                yield dent + end + post
        elif isinstance(x, dict):
            if len(x) == 0:
                yield dent + pre + '{}' + post
            else:
                yield dent + pre + '{'
                for k, v in x.items():
                    yield from go(indent, show_key(k) + ': ', v, ',')
                yield dent + '}' + post
        else:
            lines = pformat(
                x,
                sort_dicts=False,
                width=max(width-len(indent), 1),
            ).split('\n')
            if len(lines) == 1:
                yield dent + pre + lines[0] + post
            else:
                *init, last = lines
                yield dent + pre
                for line in init:
                    yield indent + line
                yield indent + last + post

    return '\n'.join(go('', '', x, ''))

import snoop
snoop.install(pformat=show)

