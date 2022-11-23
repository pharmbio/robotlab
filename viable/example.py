import viable as V
import time
from viable import Serve, Flask, call, store

serve = Serve(app := Flask(__name__))

@serve.one()
def index():
    x = store.str()
    y = store.str()
    z = store.str()
    store.assign_names(locals())
    if y.value:
        if not y.value.isdigit():
            y.assign('1')
        time.sleep(0.1)
        y.assign(str(int(y.value) + 1))
        x.assign('</script>')
    yield x.input()
    yield y.input()
    yield z.input()
    yield x.value
    yield y.value
    yield z.value
