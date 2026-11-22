#!/bin/bash
# Re-proves the flagged W = 12 windows (hpc/edge_flagged_w12.json) on any Linux
# machine: a rented VM, a cluster node, the PC. The same work as
# .github/workflows/edge-windows.yml, without GitHub.
#
#   bash hpc/run_flagged.sh ROOMS_B64_FILE [QUERIES_AT_ONCE]
#
# ROOMS_B64_FILE: Chapter 1's rooms, packed on the machine that has the game:
#   tar -czf - -C rooms/vanilla $(ls rooms/vanilla | grep '^1a_lvl_') | base64 -w0 > ch1_rooms.b64
# (they come from the game's map and are never committed.)
# QUERIES_AT_ONCE: default MemAvailable / 8 GB (a CBMC query took up to 7.2 GB
# on GitHub runners, the largest of 620).
#
# Environment: TIMEOUT (seconds per query, default 5400), LIMIT (only the first N
# windows, for a test), ROOMS (space separated rooms, default all).
#
# Resumable: a window with a finished build/cert/w12/<room>_k<K>/windows.json is
# skipped, so rerunning after an interruption (or a stopped VM) carries on.
# Results: results/edge_rerun/ (summary) and results/edge_rerun.tgz to copy back.
set -euo pipefail
cd "$(dirname "$0")/.."
B64=${1:?usage: hpc/run_flagged.sh ROOMS_B64_FILE [QUERIES_AT_ONCE]}
TIMEOUT=${TIMEOUT:-5400}

for tool in gcc python3 cbmc; do
    command -v "$tool" >/dev/null || { echo "$tool is missing: sudo apt-get install -y gcc python3 cbmc" >&2; exit 1; }
done

mkdir -p rooms/vanilla
base64 -d "$B64" | tar -xzf - -C rooms/vanilla

MEM_GB=$(awk '/MemAvailable/ {printf "%d", $2 / 1048576}' /proc/meminfo)
N=${2:-$(( MEM_GB / 8 > 0 ? MEM_GB / 8 : 1 ))}
CORES=$(nproc)
[ "$N" -le "$CORES" ] || N=$CORES

# one window per job, so the queries spread evenly over the machine
CFG=build/edge_run_local.json
mkdir -p build
python3 - <<EOF
import json, os
rooms = os.environ.get("ROOMS", "").split() or None
json.dump({"rooms": rooms, "size": 1, "limit": int(os.environ.get("LIMIT", "0")),
           "parallel": 1, "timeout": $TIMEOUT}, open("$CFG", "w"))
EOF
python3 hpc/edge_chunks.py "$CFG" 2>/dev/null | python3 -c "
import json, sys
for j in json.load(sys.stdin)['include']: print(j['room'], j['k0'], j['name'])" > build/edge_jobs.txt
TOTAL=$(wc -l < build/edge_jobs.txt)
echo "$TOTAL windows, $N at a time, ${MEM_GB} GB free, $CORES cores, timeout ${TIMEOUT}s"

prove() {   # room k name
    local R=$1 K=$2 NAME=$3 OUT=build/cert/w12/$3
    [ -f "$OUT/windows.json" ] && return 0
    mkdir -p "build/chain_tas/$R"
    cp "results/leonardo/chain_tas/$R/route.tas" "build/chain_tas/$R/route.tas"
    local START=()
    if [ -f "hpc/entry_states/ch1/entry_$R.h" ]; then
        cp "hpc/entry_states/ch1/entry_$R.h" "build/chain_tas/entry_$R.h"
        START=(--start "build/chain_tas/entry_$R.h")
    fi
    mkdir -p build/logs
    /usr/bin/time -v python3 tools/windows.py "rooms/vanilla/1a_$R.txt" "build/chain_tas/$R/route.tas" \
        "${START[@]}" --width 12 --from "$K" --to "$K" --jobs 1 --timeout "$TIMEOUT" --out "$OUT" \
        > "build/logs/$NAME.log" 2>&1 || echo "FAILED $NAME (see build/logs/$NAME.log)"
    echo "done $NAME: $(grep -E ' (no|YES|yes|timeout) \(' "build/logs/$NAME.log" | head -1 | sed 's/^ *//')"
}
export -f prove
export TIMEOUT

xargs -a build/edge_jobs.txt -P "$N" -L 1 bash -c 'prove "$0" "$1" "$2"'

# tally, in the layout hpc/edge_collect.py reads
rm -rf build/artifacts && mkdir -p build/artifacts
for d in build/cert/w12/*/; do
    n=$(basename "$d"); mkdir -p "build/artifacts/edge-$n"
    cp "$d/windows.json" "build/artifacts/edge-$n/" 2>/dev/null || true
    cp "build/logs/$n.log" "build/artifacts/edge-$n/run.log" 2>/dev/null || true
    cp "$d"/win_*_better*.tas "build/artifacts/edge-$n/" 2>/dev/null || true
done
python3 hpc/edge_collect.py build/artifacts results/edge_rerun | tee results/edge_rerun/summary.md
tar -czf results/edge_rerun.tgz -C results edge_rerun
echo "copy results/edge_rerun.tgz back; then stop or delete the machine"
