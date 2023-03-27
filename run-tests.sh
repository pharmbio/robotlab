#!/usr/bin/env bash
set -e
set -u
set -o pipefail
( cd cellpainter; set -o pipefail; cellpainter --list-imports | tee /dev/stderr | xargs pyright )
( cd labrobots; pytest )
( cd pbutils; pytest; )
( cd viable; pytest; )
python gui-tests.py
( cd cellpainter; ./cli-tests.sh )
