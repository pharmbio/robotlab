#!/bin/sh

set -euo pipefail

with-tail () {
    {
        set -x
        "$@"
    } | tail
}

test_cellpainter() {
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'Mito, plate 1'
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'Mito, plate 2'
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'PFA, plate 1'
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'PFA, plate 2'
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'Triton, plate 1'
    with-tail cellpainter --cell-paint 1,1,1 --start-from-stage 'Triton, plate 2'
    with-tail cellpainter --cell-paint 5,5,5
    with-tail cellpainter --cell-paint 6,6,6 --interleave
    with-tail cellpainter --cell-paint 7,7 --interleave
    with-tail cellpainter --cell-paint 8,8 --interleave --lockstep-threshold 8
    with-tail cellpainter --cell-paint 8,8 --interleave --two-final-washes
    with-tail cellpainter --cell-paint 8,8 --interleave --two-final-washes --start-from-stage 'Mito, plate 3'
    with-tail cellpainter --cell-paint 8,8 --interleave --two-final-washes --start-from-stage 'PFA, plate 4'
    with-tail cellpainter --cell-paint 8,8 --interleave --two-final-washes --start-from-stage 'Triton, plate 5'
    with-tail cellpainter --cell-paint 9,9 --interleave --two-final-washes
    with-tail cellpainter --cell-paint 10 --interleave --two-final-washes --incu 1260,1260,1260,1260,1290
    with-tail cellpainter --cell-paint 10 --interleave --two-final-washes --incu 1260 --protocol-dir automation_v4.0
    with-tail cellpainter --incu-load --num-plates 21
    with-tail cellpainter --time-bioteks
    with-tail cellpainter --wash-plates-clean --num-plates 11
}

test_add_estimates() {
    tmp_json=$(mktemp --suffix -cellpainter-estimates.json)
    tmp_db=$(mktemp --suffix -cellpainter-log.db)
    trap "rm -f $tmp_db $tmp_json" EXIT
    printf '%s' '{}' > "$tmp_json"
    with-tail cellpainter --robotarm 'gripper init and check' --log-filename "$tmp_db"
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
