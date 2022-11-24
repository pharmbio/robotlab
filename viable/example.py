import viable as V
import time
from viable import Serve, Flask, call, store, js, div

serve = Serve(app := Flask(__name__))

@serve.one()
def index():
    x = store.str()
    y = store.str()
    z = store.str()
    store.assign_names(locals())
    if y.value and 0:
        if not y.value.isdigit():
            y.assign('1')
        time.sleep(0.1)
        y.assign(str(int(y.value) + 1))
        x.assign('</script>')
    yield div(
        x.input(),
        y.input(),
        z.input(),
        x.value,
        y.value,
        z.value,
    )
    for i in range(3):
        yield V.button(f'bla {i}', onclick=call(lambda t=js('this.outerHTML'): print(t)))
        yield V.button(f'blap {i}', onclick=call(print, js('this.outerHTML')))
