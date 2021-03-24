
from pprint import pformat

class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

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

class Expand():
    '''
    A copy of Haskell's enum literals which look like [1..10] and [1,3..10].

    >>> expand[1, ..., 5]
    [1, 2, 3, 4, 5]
    >>> expand[5, ..., 1]
    [5, 4, 3, 2, 1]
    >>> expand[1, 3, ..., 7]
    [1, 3, 5, 7]

    Support for string prefixes, then it returns list of strings:
    >>> print(*expand.h[1, ..., 5])
    h1 h2 h3 h4 h5
    >>> print(*expand.x[8, 6, ..., 0])
    x8 x6 x4 x2 x0

    Implemented using range so unfortunately it overshoots:
    >>> expand[1, 3, ..., 8]
    [1, 3, 5, 7, 9]
    >>> expand[18, 13, ..., 0]
    [18, 13, 8, 3, -2]
    '''
    def __init__(self, prefix=None):
        self.prefix = prefix

    def __getitem__(self, args):
        out = None
        if len(args) == 3:
            start, ellipsis, stop = args
            if ellipsis == ...:
                d = 1 if start < stop else -1
                out = range(start, stop+d, d)
        elif len(args) == 4:
            start, next, ellipsis, stop = args
            if ellipsis == ...:
                d = next - start
                out = range(start, stop+d, d)
        if out is None:
            raise ValueError(f'{args} not of right shape')
        if self.prefix:
            return [self.prefix + str(i) for i in out]
        else:
            return list(out)

    def __getattr__(self, prefix):
        if not prefix.startswith('_') and prefix not in self.__dict__:
            if self.prefix is not None:
                raise ValueError(f'there is already a prefix {self.prefix!r}')
            return Expand(prefix)

expand = Expand()
