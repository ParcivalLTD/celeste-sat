# Certificates: checked proofs for the windows' "no" answers

`tools/windows.py` takes CBMC's word for every "no": no 8 (or 12, 16)
inputs get from the route's state after K frames to its state after K + W + 1
frames. Here each "no" also comes with a proof that a separate program has
checked. `tools/certify.py` asks CBMC for the same formula as DIMACS CNF
(`--dimacs`), solves it with CaDiCaL, which writes a DRAT proof, and checks
the proof with drat-trim. CBMC's own verdict and CaDiCaL's must agree, or the
run stops. A window is **certified** when CBMC says no, CaDiCaL says UNSAT
and drat-trim says `s VERIFIED`. Timeouts and anything else are recorded,
never dropped.

## What has been certified

<!-- results: python3 tools/certificates_table.py results/certificates/*.json -->
The demo room `ledge`: every 8-frame window of its 18-frame route certifies.
The CNF of K = 0 is bit for bit the one of the hand run.

**rooms/ledge.txt**, route `results/routes/ledge.tas` (leaves on frame 18), W = 8: **9 of 9 windows certified**.

| K | frames | variables | clauses | CBMC | CaDiCaL | s | proof MB | drat-trim | s |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1–9 | 3,628,991 | 11,105,266 | no (481 s) | unsat | 558 | 1,107 | verified | 1153 |
| 1 | 2–10 | 2,132,779 | 6,490,247 | no (58 s) | unsat | 190 | 563 | verified | 250 |
| 2 | 3–11 | 2,625,978 | 8,028,169 | no (137 s) | unsat | 269 | 726 | verified | 455 |
| 3 | 4–12 | 3,119,688 | 9,568,246 | no (173 s) | unsat | 384 | 924 | verified | 692 |
| 4 | 5–13 | 3,614,013 | 11,110,675 | no (242 s) | unsat | 513 | 1,199 | verified | 1151 |
| 5 | 6–14 | 3,361,482 | 10,329,572 | no (122 s) | unsat | 278 | 1,126 | verified | 539 |
| 6 | 7–15 | 3,356,305 | 10,311,355 | no (83 s) | unsat | 242 | 937 | verified | 443 |
| 7 | 8–16 | 3,356,288 | 10,311,303 | no (135 s) | unsat | 173 | 884 | verified | 413 |
| 8 | 9–17 | 3,360,795 | 10,324,948 | no (177 s) | unsat | 249 | 1,079 | verified | 694 |

Time per step, summed over the windows: CBMC 27 min, CNF export 2 min, CaDiCaL 48 min, drat-trim 96 min; proofs 8.5 GB in all (checked, then deleted).
Tools: 5.95.1 (cbmc-5.95.1); CaDiCaL 1.7.3; drat-trim binary sha256 fcc6f026604615b98830dc70e62dcea2518a0437c6df3673ffa0d41e473cd9d7.

**Chapter 1, room 1** (`lvl_1`, the community TAS, 92 frames, W = 8: 83
windows) is next. It needs the game's map file, so it runs on a machine with
the game. See "Reproducing" below. It goes to `lvl_1_w8.json`.

Files: `<room>_w<W>.json` (one row per window: K, field mask, variables,
clauses, every verdict and its seconds, proof size, SHA-256 of the CNF and
the proof, tool versions), [versions.txt](versions.txt), and
[hand_run_ledge_k0.md](hand_run_ledge_k0.md) (one window by hand, every
command).

## The pipeline can say no

`python3 tools/certify.py --self-check` (also part of
`tools/run_tests.sh --sat`) runs it where the answers are known:

1. **A known yes.** The demo room `ledge` with a wasted first frame
   (`tests/fixtures/ledge_wasted.tas`), window K = 0, W = 4: CBMC finds a
   faster route and CaDiCaL says SAT (1.6 million variables, 4.9 million clauses).
2. **A known no.** The window after it (K = 1) certifies (proof 314 MB).
3. **A broken proof.** The same window's proof written as text
   (`cadical --no-binary`, 14.5 million lines), with its last tenth cut off:
   drat-trim says `s NOT VERIFIED`.

## What the certificates prove, and what stays trusted

After the run, CaDiCaL and CBMC's own solver run no longer need to be trusted: every "no"
comes with a proof that drat-trim, a much simpler program, has checked.
What is still trusted:

- **CBMC's translation** of `harness/window.c` into the CNF: unrolling W
  frames, bit-precise float and integer arithmetic, the assumptions on
  inputs. This is now the biggest piece.
- **The model itself.** It is validated by recordings and fuzzing, not
  proven equal to the game ([docs/verification.md](../../docs/verification.md)).
- **The question the harness asks**: the same state, one frame sooner.
- **The field mask** from `sim/live.c`, which is a test, not a proof
  ([docs/methods.md](../../docs/methods.md)).
- **drat-trim**, unless it is replaced by a formally verified checker such as
  cake_lpr (LRAT proofs, `cadical --lrat` in CaDiCaL 1.9 and later).

## Reproducing

Linux or WSL (Ubuntu 24.04):

```bash
sudo apt install -y gcc python3 cbmc cadical
bash tools/get_drat_trim.sh                        # builds build/drat-trim/drat-trim
export PATH="$PWD/build/drat-trim:$PATH"
python3 tools/certify.py --self-check              # about 6 minutes
python3 tools/certify.py rooms/ledge.txt results/routes/ledge.tas --width 8 --jobs 3
```

Chapter 1, room 1 (needs `game/1-ForsakenCity.bin`, see [game/README.md](../../game/README.md)):

```bash
python3 tests/chain_tas.py                         # writes rooms/vanilla/1a_lvl_1.txt and build/chain_tas/lvl_1/route.tas
python3 tools/certify.py rooms/vanilla/1a_lvl_1.txt build/chain_tas/lvl_1/route.tas --width 8 --jobs 2
#   -> results/certificates/lvl_1_w8.json; if it is interrupted, run it again with --resume
python3 tools/certificates_table.py results/certificates/lvl_1_w8.json
```

Each job needs up to about 3 GB of memory while drat-trim checks a proof, and
the proofs (up to about 1 GB per window on `ledge`) are deleted once checked
(`--keep` keeps them). Watch the disk anyway.
