#!/bin/bash
set -eu

run() {
    (
        server="$1"; shift
        needle="$1"; shift
        request="$1"; shift

        d=$(mktemp -d --suffix=-run-tests)
        trap "rm -rf $d" EXIT

        $server > "$d/stdout" 2>/dev/null &
        gui_pid=$!
        trap "echo running trap; rm -rf $d; kill -9 $gui_pid; true" EXIT

        tail -f "$d/stdout" | while IFS='\n' read line; do
            # printf '%s\n' "$line" >&2
            if test "$line" = "$needle"; then
                eval "$request" > "$d/data"
                break
            fi
        done

        cat "$d/data"
    )
}

CDPATH=

(
    cd cellpainter
    run 'cellpainter-gui --dry-run'              'Running app...' 'curl -s localhost:5000' | grep 'incubation times:'
    run 'cellpainter-moves --dry-run'            'Running app...' 'curl -s localhost:5000' | grep 'wash_to_disp'
    run 'cellpainter --cell-paint 2 --visualize' 'Running app...' 'curl -s localhost:5000' | grep 'plate  1 incubation'
    run 'cellpainter --cell-paint 2 --visualize' 'Running app...' 'curl -s localhost:5000?cmdline=--cell-paint+3' | grep 'plate  3 incubation'
)

(
    cd imager
    run 'pf-moves --dry-run' 'Running app...' 'curl -s localhost:5000' | grep 'fridge-to-H12'
    run 'imager-gui'         'Running app...' 'curl -s localhost:5051?page=system' | grep 'test-comm:'
)
