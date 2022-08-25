
import os
import sys
import time
import textwrap
from subprocess import Popen
from pathlib import Path

autohotkey_bin = Path(r"C:\Program Files\AutoHotkey\AutoHotkey.exe")
lhc_bin = r"C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\Liquid Handling Control.exe"

protocols_path = Path(r"C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols")

def mkdir(p):
    if not p.exists():
        p.mkdir(parents=True)

dest_path = Path(r"C:\pharmbio\scratch")
mkdir(dest_path)

def save(filename):
    os.chdir(Path(lhc_bin).parent)

    LHC_NAME = filename.name
    PDF_PATH = dest_path / filename.parts[-2] / filename.with_suffix('.pdf').name

    mkdir(PDF_PATH.parent)
    if PDF_PATH.exists():
        PDF_PATH.unlink()

    print('Processing', LHC_NAME)
    print('Saving to', PDF_PATH)

    script = r"""
    SetKeyDelay, 10
    SetTitleMatchMode, RegEx
    WinWait LHC_NAME.*
    WinActivate LHC_NAME.*
    Click, 25 40
    Click, 50 225
    WinWait Print
    WinActivate Print
    Send {Enter}
    WinWait Save Print Output As
    WinActivate Save Print Output As
    Send {Raw}PDF_PATH
    Send {Enter}
    WinActivate LHC_NAME.*
    Send {Alt}{Up}{Up}{Enter}
    """
    script = script.replace("LHC_NAME", LHC_NAME)
    script = script.replace("PDF_PATH", str(PDF_PATH))
    script = textwrap.dedent(script)
    script = "\nSleep, 150\n".join(script.split("\n"))

    script_filename = dest_path / "script.ahk"
    script_filename.write_text(script)

    print("Running LHC")
    p1 = Popen([lhc_bin, filename])
    time.sleep(5)
    print("Running autohotkey")
    p2 = Popen([autohotkey_bin, script_filename], stdout=sys.stdout, stderr=sys.stderr)
    p2.wait()
    print("Done: autohotkey")
    p1.wait()
    print("Done: LHC")
    print()

def main(*args):
    one = '--one' in args
    for arg in args:
        if arg == '--one':
            continue
        workdir = protocols_path / arg
        for filename in workdir.glob('*.lhc'):
            save(filename)
            if one:
                break
    print('All done')

if __name__ == '__main__':
    main(*sys.argv[1:])
