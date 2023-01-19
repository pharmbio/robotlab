from threading import Thread
import time

import labrobots

def server():
    labrobots.Example().serve()

def main():
    s = Thread(target=server, daemon=True)
    s.start()

    time.sleep(1)

    ex = labrobots.Example().remote()
    res = ex.echo.echo('1', '2', three=4)
    print(f'{res = !r}')
    assert res == "echo ('1', '2') {'three': 4}"
    try:
        res = ex.echo.error('1', '2', three=4)
        raise ValueError(f'{res = !r} but expected error')
    except Exception as e:
        print(f'{e = }')
        assert str(e) == '''ValueError("error ('1', '2') {'three': 4}")'''
    print('success!')

if __name__ == '__main__':
    main()
