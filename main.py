from __future__ import annotations

from robotarm import Robotarm

def main():
    arm = Robotarm.init()
    arm.flash()
    arm.quit()

if __name__ == '__main__':
    main()

