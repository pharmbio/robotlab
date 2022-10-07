
import os
import sys
import time
import textwrap
from subprocess import Popen

def save(file):
    os.chdir(r"C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22")

    script = r"""
    SetKeyDelay, 10
    SetTitleMatchMode, RegEx
    WinWait FILE_LHC.*
    WinActivate FILE_LHC.*
    Click, 25 40
    Click, 50 225
    WinWait Print
    WinActivate Print
    Send {Enter}
    WinWait Save Print Output As
    WinActivate Save Print Output As
    Send {Raw}FILE_PDF
    Send {Enter}
    WinActivate FILE_LHC.*
    Send {Alt}{Up}{Up}{Enter}
    """
    script = textwrap.dedent(script)

    file_lhc = file.split("\\")[-1]
    file_pdf = file_lhc.split(".")[0] + ".pdf"
    file_pdf = "C:\\pharmbio\\" + file_pdf
    script = script.replace("FILE_LHC", file_lhc)
    script = script.replace("FILE_PDF", file_pdf)
    script = "\nSleep, 50\n".join(script.split("\n"))

    ahk_filepath = "C:\\pharmbio\\ahk.ahk"

    if os.path.exists(file_pdf):
        os.remove(file_pdf)

    with open(ahk_filepath, "w") as fp:
        fp.write(script)

    p = Popen([r"C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\Liquid Handling Control.exe", file])
    time.sleep(5)
    print("Running ahk")
    p2 = Popen([r"C:\Program Files\AutoHotkey\AutoHotkey.exe", ahk_filepath], stdout=sys.stdout, stderr=sys.stderr)
    p2.wait()
    print("ahk done")
    p.wait()
    print("lhc done")

files = []
path = r"C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\automation_v3.1"
for file in os.listdir(path):
    if file.lower().endswith('.lhc'):
        files += [path + "\\" + file]

for file in files:
    print(file)
    save(file)


