#!/bin/bash
# run_tests.sh -- build everything and check it on this machine (Linux or WSL).
#
#   bash tools/run_tests.sh              unit tests, fuzz both builds, replay the saved routes, beam-search the
#                                        demo rooms (no game files and no cbmc needed; this is what CI runs)
#   bash tools/run_tests.sh --vanilla    also Chapter 1 from your copy of the game (game/1-ForsakenCity.bin, see
#                                        game/README.md): the community TAS through all 19 rooms, the recordings
#                                        from the real game in data/recordings/, and beam searches of rooms 1-3
#   bash tools/run_tests.sh --sat        also short SAT checks, one of them across a room transition (needs cbmc)
#   bash tools/run_tests.sh --vanilla --recordings DIR
#                                        also the recordings CelesteTAS wrote into DIR (your Celeste folder, e.g.
#                                        /mnt/r/SteamLibrary/steamapps/common/Celeste): every frame against the model
#   --quick                              a smaller fuzz run (10 rooms instead of 40)
#
# Needs gcc and python3 (Ubuntu/WSL: sudo apt install -y gcc python3 cbmc).
# When started from a Windows drive (/mnt/c/...), it works on a copy in
# ~/celeste-sat-run, because WSL is much faster on its own file system.
set -e
VANILLA=0; SAT=0; RECORDINGS=""; FUZZ_ROOMS=40
while [ $# -gt 0 ]; do
    case "$1" in
        --vanilla) VANILLA=1 ;;
        --sat) SAT=1 ;;
        --quick) FUZZ_ROOMS=10 ;;
        --recordings) RECORDINGS="$(cd "$2" && pwd)" || { echo "no folder $2"; exit 2; }; shift ;;
        *) echo "unknown option $1"; exit 2 ;;
    esac
    shift
done
cd "$(dirname "$0")/.."
for tool in gcc python3; do
    command -v $tool >/dev/null || { echo "missing $tool -- run: sudo apt install -y gcc python3 cbmc"; exit 1; }
done
if [ "$SAT" = 1 ] && ! command -v cbmc >/dev/null; then
    echo "missing cbmc -- run: sudo apt install -y cbmc"; exit 1
fi
ORIG=$PWD
mkdir -p "$ORIG/build"
exec > >(tee "$ORIG/build/run_tests.log") 2>&1      # a copy of this output in build/run_tests.log
if [[ "$PWD" == /mnt/* ]]; then
    echo "copying the project to ~/celeste-sat-run (faster than working on /mnt/...)"
    mkdir -p ~/celeste-sat-run
    tar --exclude=./build --exclude=./.git -cf - . | (cd ~/celeste-sat-run && tar -xf -)
    cd ~/celeste-sat-run
fi

t0=$(date +%s)
FAILED=()
step() { echo; echo "== $1   [$(( $(date +%s) - t0 )) s]"; }
check() {  # name command...: run it, indent its output, remember a failure
    local name=$1; shift
    if ! (set -o pipefail; "$@" 2>&1 | sed "s/^/  /"); then FAILED+=("$name"); echo "  FAILED: $name"; fi
}

step "machine: $(nproc) cores, $(gcc --version | head -1), $(python3 --version)"

step "unit tests of the Python library (celeste_sat/)"
check "unit tests" python3 -m unittest discover -s tests -p "test_*.py" -q

step "differential fuzzing: literal build vs solver build, $FUZZ_ROOMS random rooms"
if sh tests/diff.sh "$FUZZ_ROOMS" 300 400 > build/diff.log 2>&1; then ok=1; else ok=0; fi
grep -c identical build/diff.log | xargs echo "  rooms identical:"
grep -E "MISMATCH|symmetry rule broken" build/diff.log | sed "s/^/  /" || true
grep -E "symmetry rules|state comparison" build/diff.log | sed "s/^/  /" || true
awk '/identical/ {s += $3} END {print "  " s, "frames compared"}' build/diff.log
[ "$ok" = 1 ] || { FAILED+=("differential fuzzing (see build/diff.log)"); echo "  FAILED -- see build/diff.log"; }

step "replaying the saved routes in both builds"
replay() {  # room route
    local b=build/replay_$(basename "$1" .txt)
    mkdir -p "$b"
    gcc -O0 -I model -o "$b/gen_tables" tools/gen_tables.c && "$b/gen_tables" > "$b/tables.h"
    python3 tools/make_room.py "$1" "$b/room.h"
    gcc -O2 -I "$b" -I model -o "$b/sim" sim/sim.c
    gcc -O2 -DREFERENCE -I "$b" -I model -o "$b/sim_ref" sim/sim.c
    local fast ref
    fast=$("$b/sim" "$2" | tail -1); ref=$("$b/sim_ref" "$2" | tail -1)
    printf "  %-28s %-32s solver build: %-18s literal build: %s\n" "$1" "$2" "$fast" "$ref"
    [ "$fast" = "$ref" ] || FAILED+=("replay $2: the builds disagree")
}
replay rooms/ledge.txt results/routes/ledge.tas
replay rooms/hop.txt results/routes/hop.tas
replay rooms/dream_test.txt tests/fixtures/dream_test.tas

step "Chapter 2 mechanics: dream blocks and the Badeline chaser on the demo rooms"
check "Chapter 2 mechanics" python3 tests/test_chapter2.py

step "room transition: the C port (model/transition.h) against the Python rules (celeste_sat/transition.py)"
# the second pair carries a Badeline chaser's history across the transition,
# which is the only check of that branch (see rooms/chase_a.txt)
check "transition" python3 tools/cross.py rooms/shaft_a.txt tests/fixtures/shaft_a.tas rooms/shaft_b.txt \
    tests/fixtures/shaft_b.tas --check-transition --out build/cross_check
check "transition (chaser)" python3 tools/cross.py rooms/chase_a.txt tests/fixtures/shaft_a.tas rooms/chase_b.txt \
    tests/fixtures/shaft_b.tas --check-transition --out build/cross_check_chaser

step "beam search on the demo rooms (all cores)"
for r in ledge hop gap flat; do
    python3 tools/solve.py rooms/$r.txt --no-sat --out build/beam_$r | grep -E "^beam" | sed -E "s/ -> .*\(/ (/; s/^/  $r: /"
done

if [ "$VANILLA" = 1 ]; then
    if python3 -c "import sys; sys.path.insert(0, '.'); from celeste_sat.paths import find_map; find_map('1-ForsakenCity.bin')" 2>/dev/null; then
        step "real game: the community TAS through Chapter 1, room after room (exports rooms/vanilla/1a_*.txt)"
        check "community TAS" python3 tests/chain_tas.py
        step "real game: the recordings in data/recordings/, every frame against the model"
        check "recordings" python3 tests/recordings.py data/recordings
        step "real game: a recording from celeste-rl (downloaded) in the model"
        python3 tests/real_game.py rooms/vanilla/1a_lvl_1.txt | sed "s/^/  /" || echo "  (needs internet access to github.com)"
        for r in 1 2 3; do
            replay rooms/vanilla/1a_lvl_$r.txt results/routes/1a_lvl_$r.tas
        done
        step "beam search + polish on Chapter 1 rooms 1-3 (all cores; a few minutes each)"
        for r in 1 2 3; do
            f=rooms/vanilla/1a_lvl_$r.txt
            s=$(date +%s)
            python3 tools/solve.py $f --polish --no-sat --out build/vanilla_$r > build/vanilla_$r.log 2>&1
            echo "  room $r: $(grep -E '^# room' build/vanilla_$r/best.tas | sed 's/# room //')   ($(( $(date +%s) - s )) s)"
        done
    else
        step "Chapter 1 skipped: game/1-ForsakenCity.bin not found (see game/README.md)"
        FAILED+=("--vanilla without game/1-ForsakenCity.bin")
    fi
fi
if [ -n "$RECORDINGS" ] && [ -f rooms/vanilla/1a_lvl_1.txt ]; then
    step "real game: recordings made with CelesteTAS ($RECORDINGS), every frame against the model"
    check "recordings in $RECORDINGS" python3 tests/recordings.py "$RECORDINGS" rooms/vanilla
fi

if [ "$SAT" = 1 ]; then
    step "SAT: is the ledge route optimal once frames 1-12 are fixed? (5 free frames)"
    python3 tools/solve.py rooms/ledge.txt --tas results/routes/ledge.tas --from-frame 12 --out build/sat_ledge | grep -E "^SAT" | sed "s/^/  /"
    step "SAT across a room transition: two stacked demo rooms, a route that waits one frame too long (21 frames; expect 20)"
    python3 tools/cross.py rooms/shaft_a.txt tests/fixtures/shaft_a.tas rooms/shaft_b.txt tests/fixtures/shaft_b.tas \
        --keep 1 --target 2 --out build/cross_shaft | grep -E "^  leave|^route|^proven|^not settled" | sed "s/^/  /"
    step "SAT windows: ledge with a wasted first frame; a 4-frame window finds it, splice_tas combines it (expect 18 frames instead of 19)"
    python3 tools/windows.py rooms/ledge.txt tests/fixtures/ledge_wasted.tas --width 4 --from 0 --to 1 \
        --out build/win_ledge | grep -E "^  frames" | sed "s/ -> .*//; s/^/  /"
    check "windows + splice" python3 tools/splice_tas.py combine rooms/ledge.txt tests/fixtures/ledge_wasted.tas \
        build/win_ledge/windows.json -o build/win_ledge/combined.tas
    grep -q "^# .*18 frames instead of 19" build/win_ledge/combined.tas || FAILED+=("windows + splice: no 18-frame route")
    if [ "$VANILLA" = 1 ] && [ -f build/chain_tas/lvl_1/route.tas ]; then
        step "SAT: Chapter 1 room 1, the community TAS with frames 1-84 fixed (7 free frames)"
        python3 tools/solve.py rooms/vanilla/1a_lvl_1.txt --tas build/chain_tas/lvl_1/route.tas --from-frame 84 \
            --out build/sat_lvl1 | grep -E "^SAT" | sed "s/^/  /"
        step "SAT across the community TAS's room 1 -> 2 transition: room 1 frames 1-88 fixed, target 2 frames into room 2 (expect: proven)"
        python3 tools/cross.py rooms/vanilla/1a_lvl_1.txt build/chain_tas/lvl_1/route.tas rooms/vanilla/1a_lvl_2.txt \
            build/chain_tas/lvl_2/route.tas --keep 88 --target 2 --out build/cross_12 \
            | grep -E "^  leave|^route|^proven|^not settled" | sed "s/^/  /"
    fi
fi

# routes found here go back next to the project (build/ is not in git)
if [ "$PWD" != "$ORIG" ]; then
    for d in build/vanilla_* build/sat_*; do
        [ -f "$d/best.tas" ] && mkdir -p "$ORIG/$d" && cp "$d/best.tas" "$d/result.json" "$ORIG/$d/" 2>/dev/null || true
    done
    for d in build/cross_*; do
        [ -f "$d/result.json" ] && mkdir -p "$ORIG/$d" && cp "$d/result.json" "$ORIG/$d/" && { cp "$d/better.tas" "$ORIG/$d/" 2>/dev/null || true; }
    done
fi
if [ ${#FAILED[@]} -gt 0 ]; then
    step "FAILED: ${FAILED[*]} (log: build/run_tests.log)"
    exit 1
fi
step "all checks passed (log: build/run_tests.log)"
