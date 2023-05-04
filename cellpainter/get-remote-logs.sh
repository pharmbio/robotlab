#!/usr/bin/env bash
set -xeuo pipefail
scp 'robotlab-ubuntu:/home/pharmbio/robotlab/cellpainter/logs/*.db' logs/
scp 'pharmbio@mikro-asus:robotlab/cellpainter/logs/*.db' logs/
