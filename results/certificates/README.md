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

**Chapter 1, room 1** (`lvl_1`, the community TAS): the route is 92 frames
long, which gives 83 windows at W = 8, and **81 of them certify**.

The two that don't are K = 31 and 32 (frames 32–40 and 33–41). Madeline is in
the middle of a dash at the start of both, with 9 and 8 dash frames left
(`coWait`), so nothing pressed during the window changes what happens. CBMC
works this out while simplifying, in under a second, and writes an empty
formula (`p cnf 0 0`). An empty formula is satisfiable, which is what CaDiCaL
says, so there is nothing to solve and no proof to check: for these two
windows the "no" comes from CBMC alone. `certify.py` marks them as
**settled** (a `"settled"` field in the row) rather than certified. The first
version of the script took the empty formula for a disagreement and stopped,
which is why the run carried on with `--from 33` and these two rows were
added at the end. The empty formula contradicts CBMC's own verdict, which is now
reported upstream as [diffblue/cbmc#9548](https://github.com/diffblue/cbmc/issues/9548).

Forcing CBMC to produce a real formula by switching its simplifier off
(`--no-simplify`, `--no-propagation`, or every loop bounded at 20 with
`--unwinding-assertions`) doesn't work: symbolic execution hadn't finished
after 4 to 9 minutes.

Windows 81 and 82 are a loose end. They also start in a dash with 9 and 8
frames left, but CBMC still writes a (small) formula for them, 0.3 and 0.8
million variables, and they certify normally. Why they behave differently
from 31 and 32 hasn't been looked into yet.

**rooms/vanilla/1a_lvl_1.txt**, route `build/chain_tas/lvl_1/route.tas` (leaves on frame 92), W = 8: **81 of 83 windows certified**, 2 settled by CBMC while simplifying (no formula, no proof).

| K | frames | variables | clauses | CBMC | CaDiCaL | s | proof MB | drat-trim | s |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1–9 | 3,817,927 | 11,692,074 | no (125 s) | unsat | 379 | 1,197 | verified | 486 |
| 1 | 2–10 | 2,213,972 | 6,732,965 | no (48 s) | unsat | 211 | 646 | verified | 236 |
| 2 | 3–11 | 2,731,789 | 8,350,459 | no (70 s) | unsat | 330 | 782 | verified | 387 |
| 3 | 4–12 | 3,250,419 | 9,971,344 | no (77 s) | unsat | 337 | 1,152 | verified | 404 |
| 4 | 5–13 | 3,768,539 | 11,590,082 | no (184 s) | unsat | 546 | 1,355 | verified | 728 |
| 5 | 6–14 | 3,769,889 | 11,595,141 | no (100 s) | unsat | 368 | 1,290 | verified | 526 |
| 6 | 7–15 | 3,530,148 | 10,875,772 | no (71 s) | unsat | 295 | 1,191 | verified | 274 |
| 7 | 8–16 | 3,530,118 | 10,875,750 | no (74 s) | unsat | 226 | 915 | verified | 212 |
| 8 | 9–17 | 3,530,696 | 10,877,887 | no (65 s) | unsat | 285 | 1,000 | verified | 258 |
| 9 | 10–18 | 3,532,575 | 10,881,915 | no (74 s) | unsat | 228 | 949 | verified | 272 |
| 10 | 11–19 | 3,531,278 | 10,876,826 | no (77 s) | unsat | 270 | 1,127 | verified | 267 |
| 11 | 12–20 | 3,532,217 | 10,880,536 | no (163 s) | unsat | 244 | 1,016 | verified | 259 |
| 12 | 13–21 | 3,071,594 | 9,462,268 | no (54 s) | unsat | 182 | 789 | verified | 182 |
| 13 | 14–22 | 3,508,820 | 10,796,400 | no (60 s) | unsat | 207 | 988 | verified | 431 |
| 14 | 15–23 | 3,073,366 | 9,468,560 | no (71 s) | unsat | 239 | 748 | verified | 292 |
| 15 | 16–24 | 3,075,000 | 9,476,415 | no (56 s) | unsat | 378 | 1,026 | verified | 256 |
| 16 | 17–25 | 3,533,730 | 10,887,817 | no (86 s) | unsat | 242 | 945 | verified | 283 |
| 17 | 18–26 | 3,533,323 | 10,886,100 | no (128 s) | unsat | 354 | 1,133 | verified | 474 |
| 18 | 19–27 | 3,533,111 | 10,886,289 | no (136 s) | unsat | 333 | 996 | verified | 423 |
| 19 | 20–28 | 3,828,307 | 11,757,697 | no (190 s) | unsat | 442 | 1,372 | verified | 498 |
| 20 | 21–29 | 3,852,057 | 11,815,703 | no (116 s) | unsat | 463 | 1,210 | verified | 550 |
| 21 | 22–30 | 3,831,258 | 11,744,872 | no (111 s) | unsat | 364 | 1,073 | verified | 423 |
| 22 | 23–31 | 3,834,026 | 11,754,088 | no (108 s) | unsat | 359 | 1,182 | verified | 433 |
| 23 | 24–32 | 3,828,792 | 11,736,678 | no (110 s) | unsat | 352 | 1,052 | verified | 373 |
| 24 | 25–33 | 3,843,675 | 11,785,140 | no (108 s) | unsat | 391 | 1,025 | verified | 358 |
| 25 | 26–34 | 3,838,396 | 11,767,308 | no (97 s) | unsat | 361 | 994 | verified | 380 |
| 26 | 27–35 | 3,824,925 | 11,724,161 | no (95 s) | unsat | 304 | 970 | verified | 311 |
| 27 | 28–36 | 1,992,989 | 6,057,024 | no (26 s) | unsat | 107 | 463 | verified | 100 |
| 28 | 29–37 | 2,511,216 | 7,676,151 | no (27 s) | unsat | 183 | 634 | verified | 131 |
| 29 | 30–38 | 3,029,532 | 9,295,548 | no (41 s) | unsat | 236 | 769 | verified | 168 |
| 30 | 31–39 | 3,548,012 | 10,915,747 | no (60 s) | unsat | 263 | 1,084 | verified | 332 |
| 31 | 32–40 | 0 | 0 | no (1 s) | settled by CBMC | 0 | 0 | – | 0 |
| 32 | 33–41 | 0 | 0 | no (1 s) | settled by CBMC | 0 | 0 | – | 0 |
| 33 | 34–42 | 299,175 | 557,206 | no (2 s) | unsat | 1 | 3 | verified | 1 |
| 34 | 35–43 | 801,008 | 2,144,328 | no (6 s) | unsat | 6 | 5 | verified | 4 |
| 35 | 36–44 | 1,308,880 | 3,757,039 | no (11 s) | unsat | 46 | 246 | verified | 29 |
| 36 | 37–45 | 1,816,894 | 5,370,206 | no (16 s) | unsat | 94 | 404 | verified | 90 |
| 37 | 38–46 | 2,324,590 | 6,982,481 | no (26 s) | unsat | 113 | 513 | verified | 91 |
| 38 | 39–47 | 2,832,757 | 8,596,133 | no (49 s) | unsat | 136 | 666 | verified | 117 |
| 39 | 40–48 | 3,340,471 | 10,208,021 | no (65 s) | unsat | 184 | 773 | verified | 167 |
| 40 | 41–49 | 3,849,976 | 11,828,149 | no (86 s) | unsat | 278 | 1,201 | verified | 287 |
| 41 | 42–50 | 3,544,609 | 10,933,219 | no (76 s) | unsat | 235 | 906 | verified | 192 |
| 42 | 43–51 | 3,544,325 | 10,932,422 | no (60 s) | unsat | 257 | 977 | verified | 162 |
| 43 | 44–52 | 3,543,937 | 10,930,788 | no (73 s) | unsat | 243 | 890 | verified | 155 |
| 44 | 45–53 | 3,545,611 | 10,936,297 | no (84 s) | unsat | 275 | 1,045 | verified | 251 |
| 45 | 46–54 | 3,543,922 | 10,929,583 | no (90 s) | unsat | 276 | 1,024 | verified | 216 |
| 46 | 47–55 | 3,546,357 | 10,940,821 | no (93 s) | unsat | 272 | 952 | verified | 264 |
| 47 | 48–56 | 3,536,953 | 10,897,595 | no (127 s) | unsat | 295 | 943 | verified | 257 |
| 48 | 49–57 | 3,862,981 | 11,841,467 | no (110 s) | unsat | 387 | 1,119 | verified | 355 |
| 49 | 50–58 | 2,217,836 | 6,741,362 | no (32 s) | unsat | 136 | 565 | verified | 128 |
| 50 | 51–59 | 2,735,626 | 8,358,778 | no (51 s) | unsat | 239 | 764 | verified | 367 |
| 51 | 52–60 | 3,254,030 | 9,979,227 | no (79 s) | unsat | 390 | 1,153 | verified | 414 |
| 52 | 53–61 | 3,772,103 | 11,597,853 | no (118 s) | unsat | 466 | 1,352 | verified | 559 |
| 53 | 54–62 | 3,528,712 | 10,870,647 | no (72 s) | unsat | 231 | 823 | verified | 184 |
| 54 | 55–63 | 3,529,938 | 10,877,495 | no (74 s) | unsat | 230 | 1,000 | verified | 318 |
| 55 | 56–64 | 3,530,315 | 10,878,977 | no (113 s) | unsat | 260 | 1,128 | verified | 279 |
| 56 | 57–65 | 3,530,056 | 10,877,918 | no (103 s) | unsat | 231 | 990 | verified | 1012 |
| 57 | 58–66 | 3,863,157 | 11,830,752 | no (100 s) | unsat | 392 | 1,046 | verified | 2405 |
| 58 | 59–67 | 3,862,885 | 11,829,773 | no (150 s) | unsat | 341 | 1,179 | verified | 385 |
| 59 | 60–68 | 3,822,984 | 11,740,508 | no (168 s) | unsat | 314 | 1,108 | verified | 389 |
| 60 | 61–69 | 3,528,398 | 10,873,219 | no (115 s) | unsat | 292 | 807 | verified | 230 |
| 61 | 62–70 | 3,528,332 | 10,873,002 | no (94 s) | unsat | 264 | 917 | verified | 275 |
| 62 | 63–71 | 3,531,878 | 10,882,490 | no (100 s) | unsat | 406 | 1,108 | verified | 391 |
| 63 | 64–72 | 3,840,572 | 11,772,607 | no (120 s) | unsat | 429 | 1,180 | verified | 538 |
| 64 | 65–73 | 3,857,882 | 11,795,773 | no (153 s) | unsat | 478 | 1,216 | verified | 526 |
| 65 | 66–74 | 3,855,916 | 11,787,738 | no (115 s) | unsat | 429 | 1,464 | verified | 602 |
| 66 | 67–75 | 3,852,797 | 11,776,980 | no (129 s) | unsat | 400 | 1,200 | verified | 570 |
| 67 | 68–76 | 3,853,342 | 11,777,828 | no (140 s) | unsat | 387 | 1,288 | verified | 568 |
| 68 | 69–77 | 3,841,591 | 11,777,784 | no (117 s) | unsat | 466 | 1,412 | verified | 577 |
| 69 | 70–78 | 3,851,125 | 11,813,057 | no (124 s) | unsat | 409 | 1,186 | verified | 538 |
| 70 | 71–79 | 3,831,036 | 11,744,919 | no (117 s) | unsat | 470 | 1,103 | verified | 521 |
| 71 | 72–80 | 3,829,996 | 11,740,995 | no (115 s) | unsat | 378 | 1,069 | verified | 424 |
| 72 | 73–81 | 3,839,459 | 11,790,834 | no (134 s) | unsat | 391 | 1,117 | verified | 411 |
| 73 | 74–82 | 3,854,643 | 11,826,530 | no (111 s) | unsat | 326 | 1,025 | verified | 383 |
| 74 | 75–83 | 3,853,870 | 11,826,336 | no (112 s) | unsat | 368 | 1,058 | verified | 381 |
| 75 | 76–84 | 3,824,673 | 11,725,222 | no (83 s) | unsat | 323 | 1,058 | verified | 341 |
| 76 | 77–85 | 3,834,404 | 11,756,209 | no (94 s) | unsat | 330 | 1,007 | verified | 342 |
| 77 | 78–86 | 1,993,326 | 6,058,457 | no (24 s) | unsat | 128 | 552 | verified | 148 |
| 78 | 79–87 | 2,512,419 | 7,681,206 | no (39 s) | unsat | 202 | 675 | verified | 180 |
| 79 | 80–88 | 3,031,014 | 9,301,866 | no (50 s) | unsat | 277 | 927 | verified | 257 |
| 80 | 81–89 | 3,549,690 | 10,922,929 | no (52 s) | unsat | 323 | 1,075 | verified | 465 |
| 81 | 82–90 | 294,811 | 527,789 | no (2 s) | unsat | 1 | 1 | verified | 1 |
| 82 | 83–91 | 785,367 | 2,069,479 | no (6 s) | unsat | 4 | 6 | verified | 4 |

Time per step, summed over the windows: CBMC 117 min, CNF export 17 min, CaDiCaL 388 min, drat-trim 474 min; proofs 76.3 GB in all (checked, then deleted).
Tools: 5.95.1 (cbmc-5.95.1); CaDiCaL 1.7.3; drat-trim binary sha256 fcc6f026604615b98830dc70e62dcea2518a0437c6df3673ffa0d41e473cd9d7.

Files: `<room>_w<W>.json` (one row per window: K, field mask, variables,
clauses, every verdict and its seconds, proof size, SHA-256 of the CNF and
the proof, tool versions), [versions.txt](versions.txt), and
[hand_run_ledge_k0.md](hand_run_ledge_k0.md) (one window run step by step,
every command).

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
