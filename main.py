from __future__ import annotations

from robotarm import Robotarm, flash

def main():
    arm = Robotarm.init()
    arm.flash()
    arm.send('execute Run()')
    arm.quit()

if __name__ == '__main__':
    main()

