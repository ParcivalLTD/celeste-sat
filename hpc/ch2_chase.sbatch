#!/bin/bash
# Re-solve the Chapter 2 chase (tools/chain_chapter2.py) on one node; the beam
# search inside it is OpenMP.
#
#   sbatch --export=ALL,BEAM=500000 hpc/ch2_chase.sbatch
#
# Run only one of these per checkout: chain_chapter2.py builds every room in
# build/<room>/ whatever --out says, so two runs side by side overwrite each
# other. It also reuses build/<room>/best.tas whenever the room is entered in
# the same state as last time, so a second run at a wider beam re-solves
# nothing unless that cache is cleared (FRESH=1 below does it).
#SBATCH --job-name=ch2_chase
#SBATCH --account=EUHPC_D30_031
#SBATCH --partition=dcgp_usr_prod
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=08:00:00
#SBATCH --output=build/logs/ch2_chase_%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source hpc/env.sh

BEAM=${BEAM:-500000}
# The chase is meaningless while these rooms let her walk through invisible barriers
# (brain.md 4b): re-export them from 2-OldSite.bin first (python3 tools/import_chapter2.py).
for r in 2a_lvl_2 2a_lvl_9 2a_lvl_10; do
    if grep -q "NOT MODELLED.*invisibleBarrier" "rooms/vanilla/${r}.txt"; then
        echo "rooms/vanilla/${r}.txt has no invisible barriers yet: re-export the Chapter 2 rooms first" >&2
        exit 1
    fi
done
if [ "${FRESH:-1}" = 1 ]; then
    rm -f build/2a_lvl_*/solved_from.h
fi

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK OMP_PROC_BIND=close OMP_PLACES=cores
echo "=== Chapter 2 chase, beam width ${BEAM}, ${OMP_NUM_THREADS} threads, $(hostname) ==="
python3 tools/chain_chapter2.py --beam-width "$BEAM" --polish --out "build/chapter2_chase_${BEAM}"
