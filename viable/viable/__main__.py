import importlib
import re
import sys
import textwrap
from pathlib import Path

from . import check

if __name__ == '__main__':
    if sys.argv[1:2] == ['--check-tests']:
        for setup_py_path in Path.cwd().rglob('setup.py'):
            pkg_path = setup_py_path.parent
            for file in pkg_path.rglob('*.py'):
                if re.search(r'^\s*@check.test', file.read_text(), flags=re.MULTILINE):
                    mod = str(file.relative_to(pkg_path).with_suffix('')).replace('/', '.')
                    print('Importing', mod, 'from', file)
                    importlib.import_module(mod)
        check.run_tests(*sys.argv[2:])
    else:
        print(textwrap.dedent(f'''
            Usage: python -m viable --check-tests [REGEX]
            Runs all tests or if regex given runs matching tests.
        ''').strip())
