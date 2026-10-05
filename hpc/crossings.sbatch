#!/bin/bash
# tools/cross.py on every room change of the chained Chapter 1 TAS (what
# tests/tas_crossings.py does one seam after another), one array task per seam.
# A seam is only ~BEFORE+1 queries, so each task takes 16 cores and Slurm packs
# several onto a node.
#
#   sbatch hpc/crossings.sbatch                                    # 6 frames before, target 3 frames after
#   sbatch --export=ALL,BEFORE=10,AFTER=8 hpc/crossings.sbatch     # wider
#
# Results: build/cross_<a>_<b>_b<BEFORE>a<AFTER>/result.json, summary line in the log.
#SBATCH --job-name=ch1_cross
#SBATCH --account=EUHPC_D30_031
#SBATCH --partition=boost_usr_prod
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --array=0-17
#SBATCH --output=build/logs/cross_%A_%a.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source hpc/env.sh

BEFORE=${BEFORE:-6}
AFTER=${AFTER:-3}
TIMEOUT=${TIMEOUT:-3600}
ORDER=(lvl_1 lvl_2 lvl_3 lvl_4 lvl_3b lvl_5 lvl_6 lvl_6a lvl_6b lvl_6c lvl_7 lvl_8 lvl_8b lvl_9 lvl_9b lvl_10a lvl_11 lvl_12 lvl_12a)
A=${ORDER[$SLURM_ARRAY_TASK_ID]}
B=${ORDER[$((SLURM_ARRAY_TASK_ID + 1))]}
RA=build/chain_tas/${A}/route.tas
RB=build/chain_tas/${B}/route.tas
N=$(python3 -c "import sys; sys.path.insert(0, 'tools'); from solve import read_tas; print(len(read_tas('$RA')))")
ENTRY=build/chain_tas/entry_${A}.h
START=()
[ -f "$ENTRY" ] && START=(--start "$ENTRY")

echo "=== ${A} -> ${B}: last ${BEFORE} frames of ${A} free, target ${B} frame ${AFTER}, $(hostname) ==="
python3 tools/cross.py "rooms/vanilla/1a_${A}.txt" "$RA" "rooms/vanilla/1a_${B}.txt" "$RB" \
    ${START[@]+"${START[@]}"} \
    --keep $((N - BEFORE)) --target "$AFTER" --timeout "$TIMEOUT" --jobs "$SLURM_CPUS_PER_TASK" \
    --out "build/cross_${A}_${B}_b${BEFORE}a${AFTER}"
