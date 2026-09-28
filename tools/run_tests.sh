#!/bin/bash
# run_tests.sh -- build everything and check it on this machine (Linux or WSL).
#
#   bash tools/run_tests.sh              fuzz both builds, replay the saved routes, beam-search the demo rooms
#   bash tools/run_tests.sh --vanilla    also Chapter 1 rooms 1-3 (rooms/vanilla/*.txt, from your game): checks against
#                                        the real game (downloaded recordings) and beam searches
#   bash tools/run_tests.sh --sat        also short SAT checks, one of them across a room transition (needs cbmc)
#   bash tools/run_tests.sh --vanilla --recordings DIR
#                                        also the recordings CelesteTAS wrote into DIR (your Celeste folder, e.g.
#                                        /mnt/r/SteamLibrary/steamapps/common/Celeste): every frame against the model
#
# Needs gcc and python3 (Ubuntu/WSL: sudo apt install -y gcc python3 cbmc).
# When started from a Windows drive (/mnt/c/...), it works on a copy in
# ~/celeste-sat-run, because WSL is much faster on its own file system.
set -e
VANILLA=0; SAT=0; RECORDINGS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --vanilla) VANILLA=1 ;;
        --sat) SAT=1 ;;
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
step() { echo; echo "== $1   [$(( $(date +%s) - t0 )) s]"; }

step "machine: $(nproc) cores, $(gcc --version | head -1)"

step "differential fuzzing: literal build vs solver build, 40 random rooms"
sh tests/diff.sh 40 300 400 > /tmp/celeste-diff.log 2>&1 && ok=1 || ok=0
grep -c identical /tmp/celeste-diff.log | xargs echo "rooms identical:"
grep -E "MISMATCH|symmetry rule broken" /tmp/celeste-diff.log || true
grep -E "symmetry rules|state comparison" /tmp/celeste-diff.log || true
awk '/identical/ {s += $3} END {print s, "frames compared"}' /tmp/celeste-diff.log
[ "$ok" = 1 ] || { echo "FAILED -- see /tmp/celeste-diff.log"; exit 1; }

step "replaying the saved routes"
replay() {  # room tas expected
    local b=build/replay_$(basename "$1" .txt)
    mkdir -p $b
    gcc -O0 -I model -o $b/gen_tables tools/gen_tables.c && $b/gen_tables > $b/tables.h
    python3 tools/make_room.py "$1" $b/room.h
    gcc -O2 -I $b -I model -o $b/sim sim/sim.c
    gcc -O2 -DREFERENCE -I $b -I model -o $b/sim_ref sim/sim.c
    printf "  %-28s %-26s solver build: %-18s literal build: %s\n" "$1" "$2" \
        "$($b/sim "$2" | tail -1)" "$($b/sim_ref "$2" | tail -1)"
}
replay rooms/ledge.txt results/ledge.tas
replay rooms/hop.txt results/hop.tas
if [ "$VANILLA" = 1 ]; then
    for r in 1 2 3; do
        [ -f rooms/vanilla/1a_lvl_$r.txt ] && [ -f results/1a_lvl_$r.tas ] && replay rooms/vanilla/1a_lvl_$r.txt results/1a_lvl_$r.tas
    done
fi

if [ "$VANILLA" = 1 ] && [ -f rooms/vanilla/1a_lvl_1.txt ]; then
    step "real game: replaying a recording from celeste-rl (downloaded) in the model"
    python3 tests/real_game.py rooms/vanilla/1a_lvl_1.txt | sed "s/^/  /" || echo "  (needs internet access to github.com)"
    step "real game: the community TAS of Chapter 1 (downloaded), rooms 1-3 in sequence"
    python3 tests/community_tas.py rooms/vanilla | sed "s/^/  /" || echo "  (needs internet access to github.com, and rooms 1-3 exported)"
fi
if [ -n "$RECORDINGS" ] && [ -f rooms/vanilla/1a_lvl_1.txt ]; then
    step "real game: recordings made with CelesteTAS ($RECORDINGS), every frame against the model"
    python3 tests/recordings.py "$RECORDINGS" rooms/vanilla | sed "s/^/  /"
fi

step "beam search on the demo rooms (all cores)"
for r in ledge hop gap flat; do
    python3 tools/solve.py rooms/$r.txt --no-sat --out build/beam_$r | grep -E "^beam" | sed -E "s/ -> .*\(/ (/; s/^/  $r: /"
done

if [ "$VANILLA" = 1 ]; then
    step "beam search + polish on Chapter 1 rooms 1-3 (all cores; a few minutes each)"
    for r in 1 2 3; do
        f=rooms/vanilla/1a_lvl_$r.txt
        [ -f $f ] || { echo "  $f not found (export it with tools/import_map.py)"; continue; }
        s=$(date +%s)
        python3 tools/solve.py $f --polish --no-sat --out build/vanilla_$r > build/vanilla_$r.log 2>&1
        echo "  room $r: $(grep -E '^# room' build/vanilla_$r/best.tas | sed 's/# room //')   ($(( $(date +%s) - s )) s)"
    done
fi

if [ "$SAT" = 1 ]; then
    step "SAT: is the ledge route optimal once frames 1-12 are fixed? (5 free frames)"
    python3 tools/solve.py rooms/ledge.txt --tas results/ledge.tas --from-frame 12 --out build/sat_ledge | grep -E "^SAT" | sed "s/^/  /"
    step "SAT across a room transition: two stacked demo rooms, a route that waits one frame too long (21 frames; expect 20)"
    python3 tools/cross.py rooms/shaft_a.txt tests/shaft_a.tas rooms/shaft_b.txt tests/shaft_b.tas --keep 1 --target 2 \
        --out build/cross_shaft | grep -E "^  leave|^route|^proven|^not settled" | sed "s/^/  /"
    if [ "$VANILLA" = 1 ] && [ -f rooms/vanilla/1a_lvl_1.txt ]; then
        if [ -f build/community_tas/lvl_1/route.tas ]; then     # downloaded by tests/community_tas.py above
            step "SAT: Chapter 1 room 1, the community TAS with frames 1-84 fixed (7 free frames)"
            python3 tools/solve.py rooms/vanilla/1a_lvl_1.txt --tas build/community_tas/lvl_1/route.tas --from-frame 84 --out build/sat_lvl1 | grep -E "^SAT" | sed "s/^/  /"
        else
            step "SAT: Chapter 1 room 1, frames 1-91 of the saved route fixed (7 free frames)"
            python3 tools/solve.py rooms/vanilla/1a_lvl_1.txt --tas results/1a_lvl_1.tas --from-frame 91 --out build/sat_lvl1 | grep -E "^SAT" | sed "s/^/  /"
        fi
        if [ -f build/community_tas/lvl_2/route.tas ] && [ -f rooms/vanilla/1a_lvl_2.txt ]; then
            step "SAT across the community TAS's room 1 -> 2 transition: room 1 frames 1-88 fixed, target 2 frames into room 2 (expect: proven)"
            python3 tools/cross.py rooms/vanilla/1a_lvl_1.txt build/community_tas/lvl_1/route.tas rooms/vanilla/1a_lvl_2.txt \
                build/community_tas/lvl_2/route.tas --keep 88 --target 2 --out build/cross_12 \
                | grep -E "^  leave|^route|^proven|^not settled" | sed "s/^/  /"
        fi
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
step "done (log: build/run_tests.log)"
