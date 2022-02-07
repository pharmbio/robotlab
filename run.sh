#!/usr/bin/env bash

function sync-files {
    set -x
    rsync -rtuv ./* robotlab-ubuntu:imx-pharmbio-automation
    # rsync -rtuv robotlab-ubuntu:imx-pharmbio-automation/logs/ logs/
    # rsync -rtuv robotlab-ubuntu:imx-pharmbio-automation/movelists/ movelists/
}

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

function imx-send {
    cmd="$1"
    quoted=$(printf %q "msg=1,$cmd")
    set -x
    ssh robotlab-ubuntu curl -s 10.10.0.99:5050 --data-urlencode "$quoted"
}

"$@"
