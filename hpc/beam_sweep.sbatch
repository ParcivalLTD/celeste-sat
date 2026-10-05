#!/bin/bash
# Beam polish of the community TAS, room by room, over a sweep of rollouts
# (ROADMAP Phase 0 item 5 / brain.md 5: rollout is not monotone and the
# defaults disagree, 8 in solve.py vs 10 in beam.c). Each task: one room,
# one rollout; tools/solve.py --tas <TAS route> --polish restarts the beam
# from frames of the TAS's own route, each room entered as the TAS enters it.
#
#   sbatch hpc/beam_sweep.sbatch                          # 19 rooms x rollouts 6..14, width 100000
#   sbatch --export=ALL,WIDTH=1000000 hpc/beam_sweep.sbatch
#
# A faster room here leaves in a different state, so it is a candidate, not a
# saving: the next room has to be checked from it (tools/cross.py, tools/chapter.py).
# Result line per task in the log: "RESULT room rollout width tas_frames polished_frames".
#SBATCH --job-name=beam_sweep
#SBATCH --account=EUHPC_D30_031
#SBATCH --partition=boost_usr_prod
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=100G
#SBATCH --time=01:00:00
#SBATCH --array=0-170
#SBATCH --output=build/logs/sweep_%A_%a.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source hpc/env.sh

WIDTH=${WIDTH:-100000}
ROLLOUTS=(6 7 8 9 10 11 12 13 14)
ORDER=(lvl_1 lvl_2 lvl_3 lvl_4 lvl_3b lvl_5 lvl_6 lvl_6a lvl_6b lvl_6c lvl_7 lvl_8 lvl_8b lvl_9 lvl_9b lvl_10a lvl_11 lvl_12 lvl_12a)
ROOM=${ORDER[$((SLURM_ARRAY_TASK_ID / ${#ROLLOUTS[@]}))]}
R=${ROLLOUTS[$((SLURM_ARRAY_TASK_ID % ${#ROLLOUTS[@]}))]}
ROUTE=build/chain_tas/${ROOM}/route.tas
ENTRY=build/chain_tas/entry_${ROOM}.h
START=()
[ -f "$ENTRY" ] && START=(--start "$ENTRY")
OUT=build/sweep/${ROOM}_r${R}_w${WIDTH}

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_PROC_BIND=close OMP_PLACES=cores
echo "=== ${ROOM} rollout ${R} width ${WIDTH}, $(hostname) ==="
python3 tools/solve.py "rooms/vanilla/1a_${ROOM}.txt" ${START[@]+"${START[@]}"} \
    --tas "$ROUTE" --polish --no-sat --beam-width "$WIDTH" --beam-rollout "$R" --out "$OUT"
TAS=$(python3 -c "import sys; sys.path.insert(0, 'tools'); from solve import read_tas; print(len(read_tas('$ROUTE')))")
GOT=$("$OUT/sim" "$OUT/best.tas" | sed -n 's/.*EXIT at frame \([0-9]*\).*/\1/p' | head -1)
echo "RESULT ${ROOM} ${R} ${WIDTH} ${TAS} ${GOT:-none}"
