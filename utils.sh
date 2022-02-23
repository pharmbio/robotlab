#!/usr/bin/env bash

function imx-send {
    msg="$1"
    quoted=$(printf %q "msg=$msg")
    set -x
    ssh robotlab-ubuntu curl -s 10.10.0.97:5050/imx --data-urlencode "$quoted"
}

"$@"
