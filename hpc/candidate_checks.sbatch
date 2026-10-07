#!/bin/bash
#SBATCH --job-name=entry_chk
#SBATCH --account=EUHPC_D30_031
#SBATCH --partition=boost_usr_prod
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=120G
#SBATCH --time=01:30:00
#SBATCH --output=build/logs/entry_checks_%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source hpc/env.sh

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_PROC_BIND=close OMP_PLACES=cores
WIDTH=${WIDTH:-500000}
mkdir -p build/checks

JOBS=(
  "1a_lvl_6b entry_lvl_6b_after_6a_118 153"
  "1a_lvl_12a entry_lvl_12a_after_12_143 145"
  "1a_lvl_12a entry_lvl_12a_after_12_140 148"
)

for job in "${JOBS[@]}"; do
    set -- $job
    ROOM=$1
    ENTRY_NAME=$2
    THRESHOLD=$3
    OUT="build/checks/out_${ENTRY_NAME}_w${WIDTH}"
    echo "================================================================================"
    echo "=== Running ${ROOM} with start ${ENTRY_NAME} (Beam width: ${WIDTH}) ==="
    echo "=== Target threshold: < ${THRESHOLD} frames to beat the community TAS ==="
    echo "================================================================================"
    python3 tools/solve.py "rooms/vanilla/${ROOM}.txt" \
        --start "hpc/entry_states/${ENTRY_NAME}.h" \
        --beam-width "$WIDTH" --polish --no-sat \
        --out "$OUT"
    
    if [ -f "$OUT/best.tas" ]; then
        FRAMES=$("$OUT/sim" "$OUT/best.tas" | sed -n 's/.*EXIT at frame \([0-9]*\).*/\1/p' | head -1)
        echo "RESULT ${ROOM} ${ENTRY_NAME} frames=${FRAMES} threshold=${THRESHOLD}"
        if [ -n "$FRAMES" ] && [ "$FRAMES" -lt "$THRESHOLD" ]; then
            echo ">>> CANDIDATE FRAME SAVE! (${FRAMES} < ${THRESHOLD}) <<<"
        else
            echo ">>> Did not beat threshold (${FRAMES} >= ${THRESHOLD}) <<<"
        fi
    fi
done
