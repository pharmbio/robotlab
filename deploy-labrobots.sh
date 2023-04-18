#!/bin/bash

set -x
windows_nuc=$(python -c 'import labrobots; print(labrobots.WindowsNUC.ip)')
windows_gbg=$(python -c 'import labrobots; print(labrobots.WindowsGBG.ip)')
nikon=$(python -c 'import labrobots; print(labrobots.Nikon.ip)')

ssh devserver "
    set -x;
    curl -s $windows_gbg:5050/git/pull_and_shutdown;
    curl -s $windows_nuc:5050/git/pull_and_shutdown;
    curl -s $nikon:5050/git/pull_and_shutdown;
    curl -s $windows_gbg:5050/git/show;
    curl -s $windows_nuc:5050/git/show;
    curl -s $nikon:5050/git/show;
"
