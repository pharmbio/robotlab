#!/bin/bash

set -euo pipefail

with-tail () {
    {
        set -x
        "$@"
    } | tail
}

test_cellpainter() {
    # for i in 1,1 2,2 3,3 4,4 5,5 6,6 7,7 8,8 9,9 10; do
    for i in 1,1 2,5 6 7 8 9; do
        with-tail cellpainter --cell-paint "$i" --protocol-dir automation_v5.0 --interleave --two-final-washes
        for d in automation_v5.0_blue automation_v4.0_RMS; do
            with-tail cellpainter --cell-paint "$i" --protocol-dir "$d" --interleave
        done
    done
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'Mito, plate 1'
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'Mito, plate 2'
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'PFA, plate 1'
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'PFA, plate 2'
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'Triton, plate 1'
    with-tail cellpainter --cell-paint 1,1 --start-from-stage 'Triton, plate 2'
    with-tail cellpainter --cell-paint 6 --interleave --start-from-stage 'Mito, plate 3'
    with-tail cellpainter --cell-paint 6 --interleave --start-from-stage 'PFA, plate 4'
    with-tail cellpainter --cell-paint 6 --interleave --start-from-stage 'Triton, plate 5'
    with-tail cellpainter --incu-load --num-plates 21
    with-tail cellpainter --time-protocols
    with-tail cellpainter --wash-plates-clean --num-plates 11
}

test_add_estimates() {
    tmp_json=$(mktemp --suffix -cellpainter-estimates.json)
    tmp_db=$(mktemp --suffix -cellpainter-log.db)
    trap "rm -f $tmp_db $tmp_json" EXIT
    printf '%s' '{}' > "$tmp_json"
    with-tail cellpainter --run-robotarm 'gripper init and check' --log-filename "$tmp_db"
    with-tail cellpainter --add-estimates-from "$tmp_db" --add-estimates-dest "$tmp_json"
    cat "$tmp_json"
    printf '\n'
    {
        set -x
        test "$(grep -c times "$tmp_json")" = 1
        test "$(grep -c 'gripper init and check' "$tmp_json")" = 1
    }
}

test_cellpainter
test_add_estimates