from __future__ import annotations

from robotarm import Robotarm
import utils

def main():
    arm = Robotarm.init()
    arm.flash()
    arm.execute('Main()')
    arm.quit()

if __name__ == '__main__':
    main()

