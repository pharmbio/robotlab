#!/usr/bin/env bash
set -e
set -u
set -o pipefail
( cd cellpainter; set -o pipefail; cellpainter --list-imports | tee /dev/stderr | xargs pyright )
( cd pbutils; pytest; )
( cd viable; pytest; )
python gui-tests.py
( cd labrobots; python test.py )
( cd cellpainter; ./cli-tests.sh )
