#!/bin/sh
# Differential test: the solver build (integer timers, boundary-jump movement)
# must match the literal reference build frame by frame on random rooms and
# random inputs.  usage: tests/diff.sh [rooms] [runs-per-room] [frames]
set -e
cd "$(dirname "$0")/.."
ROOMS=${1:-30}; RUNS=${2:-300}; FRAMES=${3:-400}
mkdir -p build/fuzz
rm -f build/fuzz/coverage.txt build/fuzz/symmetry.txt
gcc -O0 -I model -o build/fuzz/gen_tables tools/gen_tables.c
./build/fuzz/gen_tables > build/fuzz/tables.h
fail=0
for seed in $(seq 1 "$ROOMS"); do
    python3 tests/random_room.py "$seed" > build/fuzz/room.txt
    python3 tools/make_room.py build/fuzz/room.txt build/fuzz/room.h
    gcc -O2 -I build/fuzz -I model -o build/fuzz/f_fast tests/fuzz.c
    gcc -O2 -DREFERENCE -DCOVERAGE -I build/fuzz -I model -o build/fuzz/f_ref tests/fuzz.c
    ./build/fuzz/f_fast "$seed" "$RUNS" "$FRAMES" > build/fuzz/a.txt 2>> build/fuzz/symmetry.txt || { echo "room $seed: symmetry rule broken"; fail=1; }
    ./build/fuzz/f_ref  "$seed" "$RUNS" "$FRAMES" > build/fuzz/b.txt 2>> build/fuzz/coverage.txt
    if cmp -s build/fuzz/a.txt build/fuzz/b.txt; then
        printf "room %3d: %7d frames identical (%s exits, %s deaths)\n" "$seed" "$(wc -l < build/fuzz/a.txt)" \
            "$(awk '$12==1' build/fuzz/a.txt | wc -l)" "$(awk '$13==1' build/fuzz/a.txt | wc -l)"
    else
        echo "room $seed: MISMATCH"; diff build/fuzz/a.txt build/fuzz/b.txt | head -5; fail=1
    fi
done
awk '/symmetry checks/ {c+=$3; b+=$5} END {printf "symmetry rules of the CBMC harness: %d checks, %d broken\n", c, b}' build/fuzz/symmetry.txt
awk '/same_future checks/ {c+=$3; b+=$5} END {printf "state comparison (same_future): %d frames checked, %d broken\n", c, b}' build/fuzz/symmetry.txt
echo "mechanics exercised (reference build, all rooms):"
awk -F'\t' '{c[$1]+=$2} END {for (k in c) printf "  %-26s %d\n", k, c[k]}' build/fuzz/coverage.txt | sort
exit $fail
