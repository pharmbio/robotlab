#!/usr/bin/env bash
set -e
set -u
set -o pipefail
pyright --version
( export PYTHONPATH="$(pwd)/pbutils:$(pwd)/labrobots:$(pwd)/viable"; cd cellpainter; set -o pipefail; cellpainter --list-imports | tee /dev/stderr | xargs pyright --verbose )
( cd labrobots; pytest )
( cd pbutils; pytest; )
( cd viable; pytest; )
( cd cellpainter; pytest; )
python gui-tests.py
( cd cellpainter; ./cli-tests.sh )
