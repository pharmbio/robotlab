try:
    builtins = __import__("__builtin__")
except ImportError:
    builtins = __import__("builtins")

def snoop_init():
    import sys
    sys.path = ['.'] + sys.path
    import utils
    import snoop
    snoop.install(pformat=utils.show)

class Proxy:
    def __init__(self, name, init):
        self.name = name
        self.init = init

    def __call__(self, *args, **kws):
        self.init()
        return getattr(builtins, self.name)(*args, **kws)

    def __getattr__(self, arg):
        self.init()
        return getattr(getattr(builtins, self.name), arg)

for name in 'pp snoop'.split():
    setattr(builtins, name, Proxy(name, snoop_init))

