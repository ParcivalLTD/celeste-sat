# Leonardo EuroHPC Verification Results & Artifacts

This directory contains the formal verification results, mathematical optimality certificates, parameter sweeps, and execution provenance generated on the **Leonardo EuroHPC Supercomputer** (`EUHPC_D30_031`, CINECA, Italy).

---

## 1. Summary of Compute & Results

* **Total Compute Consumed:** ~2,300 core-hours (95.8 core-days) across 14 job submissions (>350 batch tasks) on Leonardo Booster nodes (`lrdnXXXX`).
* **Hardware:** Atos BullSequana XH2000, 32-core custom Intel Xeon 8358 CPUs per task, 480–512 GB RAM.
* **Formal SAT Proofs (CBMC):**
  * **4,371 formal CBMC queries** evaluated.
  * **4,338 sliding windows proven mathematically optimal** (99.2% success rate, <0.8% timeouts).
  * Formal counterexamples discovered **15 frames of improvements** across Chapter 1 (`lvl_6a` -5f, `lvl_12` -5f, `lvl_9b` -3f, `lvl_3b` -2f).

To inspect the full window verification table across all rooms and widths, run from the repository root:
```bash
python3 hpc/summary.py
```

---

## 2. Directory Structure

```
results/leonardo/
├── cert/                 # Formal mathematical optimality certificates
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
└── tas_endings.json      # Optimal ending inputs for Chapter 1 rooms
```

---

## 3. Provenance & Reproduction

* **CBMC Version:** 5.80.0
* **Compiler:** GCC 12.2.0 (Spack)
* **Python:** 3.11.7
* **Cluster:** CINECA Leonardo (Booster partition: `boost_usr_prod`, Data-Centric: `dcgp_usr_prod`)
