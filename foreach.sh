#!/bin/sh
if test "$#" = 0; then
    printf "
    Specify a command to run in each package directory, such as 'pip install --editable .'
    Example:

        $0 pip install --editable .
    \n"
    exit 1
fi
set -eu
packages='
    pbutils
    viable
    labrobots
    imager
    cellpainter
'
CDPATH=
for pkg in $packages; do
    (
        cd "$pkg"
        set -x
        set -eu
        "$@"
    )
done
