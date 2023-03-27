#!/usr/bin/env bash

function forward-robot-to-localhost {
    verbose () {
        set -x
        "$@"
        set +x
    }
    verbose ssh -N -L 10000:10.10.0.98:10000 robotlab-ubuntu & pid1="$!"
    verbose ssh -N -L 10100:10.10.0.98:10100 robotlab-ubuntu & pid2="$!"
    trap "verbose kill $pid1 $pid2" EXIT
    wait
}

"$@"
