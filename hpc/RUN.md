# Leonardo runbook (2 days, account EUHPC_D30_031)

The account's hours are on the **Booster** partition (`boost_usr_prod`) only;
`saldo -b --dcgp` shows no DCGP budget for it. A Booster node is 32 Ice Lake
cores, 512 GB and 4 A100s. Nothing here uses the GPUs, so every job asks for
CPU cores only. Booster is busy (27 of 3176 nodes were free on 2026-10-05), so
submit early: short single-node jobs get through the queue fastest.

Budget: `saldo -b` on 2026-10-05 showed 95,054 local h left until 2026-11-30,
and 11,835 for this month with none used yet. Plan for about 5–8k (expected)
and stay under the monthly figure. The account may be shared, so check with
whoever else uses it before going beyond that.

How a CPU-only job on a GPU node is billed is not in CINECA's docs. Read it off
the first job that runs: `sacct -X -j <jobid> --format=JobID,AllocTRES%80`
shows `billing=N`, the local hours charged per hour of that job. If N is far
above the cores you asked for, rethink the big runs before submitting them.

Every command runs from the repo root on a login node.

## Tonight

```bash
# 0. setup
module avail gcc python                  # fix the names in hpc/env.sh if needed
source hpc/env.sh && cbmc --version
mkdir -p build/logs                      # Slurm opens the log files before the job starts
python3 tests/chain_tas.py               # writes rooms/vanilla/1a_*.txt and build/chain_tas/
                                         # must end "2275 frames of the community TAS played exactly"

# 1. smoke test on a compute node: same builds as on your laptop (fuzzer: 0 broken)?
srun -A EUHPC_D30_031 -p boost_usr_prod -c 32 --mem=60G -t 00:30:00 tools/run_tests.sh

# 2. W=12 over all of Chapter 1, plus every room change at the default window
python3 hpc/make_tasks.py --width 12     # prints the sbatch line: run it
sbatch hpc/crossings.sbatch

# 3. pilot of the beam sweep: lvl_1 at all 9 rollouts, to see how long one run takes
sbatch --array=0-8 hpc/beam_sweep.sbatch
```

Watch the per-query seconds in `build/logs/win_*.out` (`python3 hpc/summary.py`).
They calibrate the rest. The ROADMAP's laptop figures are ~8 min per query at
W=12 and ~65 min at W=16.

```bash
# 4. before bed: W=16 over Chapter 1 (timeout 4 h per query; raise it if W=12 was slow)
python3 hpc/make_tasks.py --width 16 --timeout 14400      # run the printed line
# stretch: room 1 at W=18 (12 h per query)
python3 hpc/make_tasks.py --width 18 --rooms lvl_1 --timeout 43200
# the rest of the beam sweep, if the pilot's runs took minutes, not the hour
sbatch --array=9-170 hpc/beam_sweep.sbatch
```

Chapter 2 chase: only after `2a_lvl_2`, `2a_lvl_9` and `2a_lvl_10` have been
re-exported with invisible barriers (`python3 tools/import_chapter2.py` on the
laptop, which has `2-OldSite.bin`; done on 2026-10-05, in git). Then
`sbatch --export=ALL,BEAM=500000 hpc/ch2_chase.sbatch` (32 cores, up to 12 h).
The script refuses to run while the rooms lack the barriers.

## Tomorrow

```bash
python3 hpc/summary.py                                    # windows: proven / timeout / faster
grep -h "^RESULT" build/logs/sweep_*.out | sort -k1,1 -k5n  # beam: rooms where polish beat the TAS
for f in build/logs/cross_*.out; do head -1 "$f"; tail -1 "$f"; done   # crossings
```

- **Wider crossings on the six rooms whose ending can be a frame faster**
  (`lvl_2`, `lvl_3`, `lvl_4`, `lvl_3b`, `lvl_8`, `lvl_12`): this is where a real
  saving over the TAS would show up.
  `sbatch --array=1,2,3,4,11,17 --export=ALL,BEFORE=10,AFTER=8 hpc/crossings.sbatch`
- Rerun the chunks whose windows timed out, with a longer `TIMEOUT`.
- A "faster" window or sweep result exists only in the model. Play it in the
  game (tools/celestetas.py) before calling it a saving.

## Before access ends

Copy the results home: `build/cert`, `build/cross_*`, `build/sweep`,
`build/logs`, `build/hpc`, `build/chapter2_chase_*`, e.g.

```bash
rsync -avm --include='*/' --include='*.json' --include='*.tas' --include='*.out' --exclude='*' \
    leonardo:celeste-sat/build/ ./build/leonardo/
```

Check spend with `saldo -b` (it is updated about once a day) and
`sacct -S today -X --format=JobID,JobName,Elapsed,AllocCPUS,State`.
