#!/bin/bash

set -euo pipefail

with-tail () {
    {
        set -x
        "$@"
    } | tail
}

test_cellpainter() {
    for i in 1 2 5 6 7 8 9; do
        with-tail cellpainter --cell-paint --batch-sizes "$i" --protocol-dir automation_v5.0 --interleave --two-final-washes
        for d in automation_v5.0_blue automation_v4.0_RMS; do
            with-tail cellpainter --cell-paint --batch-sizes "$i" --protocol-dir "$d" --interleave
        done
    done
    for i in 1 2 3; do
        for j in $(seq 1 $i); do
            with-tail cellpainter --cell-paint --batch-sizes "$i" --start-from-stage "Mito, plate $j"
            with-tail cellpainter --cell-paint --batch-sizes "$i" --start-from-stage "PFA, plate $j"
            with-tail cellpainter --cell-paint --batch-sizes "$i" --start-from-stage "Triton, plate $j"
        done
    done
    with-tail cellpainter --cell-paint --batch-sizes 6 --interleave --start-from-stage 'Mito, plate 3'
    with-tail cellpainter --cell-paint --batch-sizes 6 --interleave --start-from-stage 'PFA, plate 4'
    with-tail cellpainter --cell-paint --batch-sizes 6 --interleave --start-from-stage 'Triton, plate 5'
    with-tail cellpainter --incu-load --num-plates 21
    with-tail cellpainter --time-protocols
    with-tail cellpainter --wash-plates-clean --num-plates 11
}

test_add_estimates() {
    tmp_jsonl=$(mktemp --suffix -cellpainter-estimates.jsonl)
    tmp_db=$(mktemp --suffix -cellpainter-log.db)
    trap "rm -f $tmp_db $tmp_jsonl" EXIT
    touch "$tmp_jsonl"
    with-tail cellpainter --run-robotarm 'ur gripper init and check' --log-filename "$tmp_db"
    with-tail cellpainter --add-estimates-from "$tmp_db" --add-estimates-dest "$tmp_jsonl"
    cat "$tmp_jsonl"
    {
        set -x
        set -e
        test "$(grep -c 'ur gripper init and check' "$tmp_jsonl")" = 1
    }
    with-tail cellpainter --add-estimates-from "$tmp_db" --add-estimates-dest "$tmp_jsonl"
    cat "$tmp_jsonl"
    {
        set -x
        set -e
        test "$(grep -c 'ur gripper init and check' "$tmp_jsonl")" = 2
    }
}

test_cellpainter
test_add_estimates
