from pathlib import Path
import re
import sys
import difflib

for p2 in [
    Path('./automation_v5.1/'),
    Path('./automation_v4.0/'),
    Path('./automation_v4.0_copy/'),
]:
    p = Path('./automation_v5.0/')
    for i in p.glob('*.txt'):
        kind, *_ = re.split('(?<=[WD]_)', i.stem)
        for j in p2.glob('*.txt'):
            if j.stem.startswith(kind):
                a = [re.sub('  +', '  ', line) for line in i.read_text().splitlines(keepends=True) if not any(s in line for s in '\\ File Printed Revision Saved'.split())]
                b = [re.sub('  +', '  ', line) for line in j.read_text().splitlines(keepends=True) if not any(s in line for s in '\\ File Printed Revision Saved'.split())]
                thediff = list(difflib.unified_diff(a, b, fromfile=str(i), tofile=str(j), n=1))
                if thediff:
                    sys.stdout.writelines(thediff)
                    print()
