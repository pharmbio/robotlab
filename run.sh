#!/usr/bin/env bash
function sync-files {
    set -x
    rsync -rtuv ./* robotlab-ubuntu:imx-pharmbio-automation
    # rsync -rtuv robotlab-ubuntu:imx-pharmbio-automation/logs/ logs/
    # rsync -rtuv robotlab-ubuntu:imx-pharmbio-automation/movelists/ movelists/
}

"$@"
