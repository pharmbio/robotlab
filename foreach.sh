#!/bin/sh
if test "$#" = 0; then
    printf "
    Specify a command to run on each package directory, such as 'pip install --editable'
    Example:

        $0 pip install --editable
    \n"
    exit 1
fi
set -x
"$@" labrobots
"$@" imager
"$@" cellpainter
