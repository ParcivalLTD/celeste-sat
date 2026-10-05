#!/bin/bash
# One chunk of Chapter 1 window proofs per array task.
# Submit with the command hpc/make_tasks.py prints (it sets --array,
# --cpus-per-task, --mem, --time, TASKS and TIMEOUT). Results:
# build/cert/w<W>/<room>_k<k0>-<k1>/windows.json, and one line per window in
# the log as it finishes (hpc/summary.py reads both).
#SBATCH --job-name=ch1_win
#SBATCH --account=EUHPC_D30_031
#SBATCH --partition=dcgp_usr_prod
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=28
#SBATCH --mem=130G
#SBATCH --output=build/logs/win_%A_%a.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source hpc/env.sh

: "${TASKS:?set TASKS (see hpc/make_tasks.py)}"
TIMEOUT=${TIMEOUT:-3600}
read -r ROOM W K0 K1 < <(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$TASKS")
N=$((K1 - K0 + 1))

# as many queries at once as fit in this job's memory (and no more than its cores)
if [ -n "${SLURM_MEM_PER_NODE:-}" ]; then MEM_MB=$SLURM_MEM_PER_NODE
else MEM_MB=$(( $(awk '/MemAvailable/ {print $2}' /proc/meminfo) / 1024 )); fi
CAP=$(python3 -c "print(max(1, int($MEM_MB / 1.1 / ((0.3 * $W + 0.5) * 1024))))")
JOBS=$(( N < CAP ? N : CAP ))
JOBS=$(( JOBS < SLURM_CPUS_PER_TASK ? JOBS : SLURM_CPUS_PER_TASK ))

ENTRY=build/chain_tas/entry_${ROOM}.h
START=()
[ -f "$ENTRY" ] && START=(--start "$ENTRY")
OUT=build/cert/w${W}/${ROOM}_k${K0}-${K1}

echo "=== ${ROOM} W=${W} K=${K0}..${K1}: ${N} windows, ${JOBS} at a time, timeout ${TIMEOUT}s, $(hostname) ==="
python3 tools/windows.py "rooms/vanilla/1a_${ROOM}.txt" "build/chain_tas/${ROOM}/route.tas" \
    ${START[@]+"${START[@]}"} \
    --width "$W" --from "$K0" --to "$K1" --jobs "$JOBS" --timeout "$TIMEOUT" --out "$OUT"
