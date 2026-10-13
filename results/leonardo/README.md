# Leonardo EuroHPC Verification Results & Artifacts

This directory contains the formal verification results, mathematical optimality certificates, parameter sweeps, and execution provenance generated on the **Leonardo EuroHPC Supercomputer** (`EUHPC_D30_031`, CINECA, Italy).

---

## 1. Summary of Compute & Results

* **Total Compute Consumed:** ~2,300 core-hours (95.8 core-days) across 14 job submissions (>350 batch tasks) on Leonardo Booster nodes (`lrdnXXXX`).
* **Hardware:** Atos BullSequana XH2000, 32-core custom Intel Xeon 8358 CPUs per task, 480–512 GB RAM.
* **SAT proofs (CBMC), as tallied by `hpc/summary.py`:**
  * **3,920 windows** over the chained community TAS (W = 12 and 16 over all 19 rooms, W = 18 over `lvl_1`).
  * **3,899 proven**: no input sequence gets from the TAS's state at frame K to its state at frame K + W + 1 in W frames or fewer, within the model (local optimality). 6 timeouts.
  * **15 "faster" windows**, all at the end of a room (`lvl_6a`, `lvl_12`, `lvl_9b`, `lvl_3b`): the room is left 2-5 frames sooner, in a different exit state. After each, the next room's TAS inputs fail, so none of them is a chapter saving yet (see `docs/results.md`).
  * **36 room-transition queries** (18 seams × 2 window sizes, `cross/`): all proven.

To inspect the full window verification table across all rooms and widths, run from the repository root:
```bash
python3 hpc/summary.py
```

---

## 2. Directory Structure

```
results/leonardo/
├── cert/                 # window proofs (local-optimality certificates)
│   ├── w12/              # Window width W=12 (all 19 rooms of Chapter 1 certified)
│   ├── w16/              # Window width W=16 (all 19 rooms of Chapter 1 certified)
│   └── w18/              # Window width W=18 (lvl_1 fully certified, 73 windows)
├── logs/                 # Slurm batch execution logs (390 output logs, win_*.out, cross_*.out)
├── provenance/           # Cluster accounting, budgets, and environment info
│   ├── sacct.txt         # Slurm job accounting table for all tasks
│   ├── saldo.txt         # Allocation usage and remaining hours
│   └── versions.txt      # Git commit, CBMC 5.80.0, GCC 12.2.0, Python 3.11.7
├── sweep/                # 171 beam parameter sweeps (r=6..14 rollout depth)
│   └── lvl_*_r*_w100000/ # best.tas, result.json, tidy.tas, trace.json
├── cross/                # 38 room-crossing transition verification tasks
│   └── cross_*/          # result.json, known.tas, route_a.tas
├── chase/                # Chapter 2 chase room solutions from Leonardo (2a_lvl_3 .. 2a_lvl_7)
├── chain_tas/            # Chained TAS routes and entry state headers
├── checks/               # Candidate entry verification scripts and headers
└── tas_endings.json      # the TAS-endings queries (experiments/tas_endings.py)
```

---

## 3. Provenance & Reproduction

* **CBMC Version:** 5.80.0
* **Compiler:** GCC 12.2.0 (Spack)
* **Python:** 3.11.7
* **Cluster:** CINECA Leonardo (Booster partition: `boost_usr_prod`, Data-Centric: `dcgp_usr_prod`)
