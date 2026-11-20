# celeste-window: a SAT benchmark family (draft for the SAT Competition 2027)

One CNF per (room, route, K, W): CBMC's bit-precise formula for "can any W
inputs take Madeline from the route's state after K frames to its state
after K + W + 1 frames?" (`harness/window.c`, the window question of
`tools/windows.py`). UNSAT instances come with a DRAT proof checked by
drat-trim (`tools/certify.py`). SAT instances are windows with a known
faster route, which CBMC's counterexample gives. W tunes the difficulty: a
4-frame window of the demo room `ledge` has about 1.6 million variables, an
8-frame one about 3.6 million variables and 11 million clauses.

```
python3 tools/benchmark.py                                  # every instance in family.json, into build/benchmark/
python3 tools/benchmark.py --calibrate 3600                 # also time MiniSat, CaDiCaL and Kissat (whichever are installed)
python3 tools/benchmark.py --only celeste-window_ledge_w8_k0
```

The output directory holds `<name>.cnf.xz` (DIMACS with exact header counts,
CBMC's variable-name comments replaced by a three-line header) and
`metadata.json` / `metadata.csv`: room, K, W, expected answer, certified or
not, variables, clauses, SHA-256 of the uncompressed CNF, and the
calibration times. The CNFs are not committed. They are regenerated from
`family.json`, and their SHA-256 values check that a regeneration matches.

`family.json` is a first list of 21 instances on the project's own demo
rooms (`ledge`, `hop`): 3 SAT (the wasted first frame of
`tests/fixtures/ledge_wasted.tas`, W = 4, 6 and 8) and 18 UNSAT (windows of
the `ledge` and `hop` routes at W = 6 and 8). Calibrate it, then keep about
20 that take minutes, not seconds or days, with SAT and UNSAT mixed.

## Before submitting

- **Licensing.** `tools/benchmark.py` refuses rooms from `rooms/vanilla/`
  unless `--allow-game-rooms` is given: their geometry is Celeste's level data,
  which carries no licence notice, and the CNFs encode it. The demo rooms in
  `rooms/` are the project's own. Settle this before publishing anything
  built on the game's rooms.
- **Rules.** The 2026 rules ask for DIMACS CNF with exact header counts and a 1
  to 2 page description per family in IEEE Proceedings style. Check the 2027
  call when it is out (expected around January), including whether
  benchmark-only submissions are accepted.
- **Kissat** is not packaged for Ubuntu 24.04; build it from
  github.com/arminbiere/kissat and set `KISSAT` for the calibration.
