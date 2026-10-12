# Developing celeste-sat

How the code fits together, the rules that keep the results trustworthy, and
the commands you will use. The dated notes on why things are the way they
are live in [history.md](history.md).

## The one idea

One C port of Madeline's movement, compiled three ways:

| build | defined by | used for |
|---|---|---|
| **reference** | `-DREFERENCE` | literal float timers, pixel-by-pixel movement. The oracle. |
| **solver** | (default) | integer frame counters from `tools/gen_tables.c`, boundary-jump movement, an 8×8-tile collision window. Must be bit-identical to the reference. |
| **CBMC harness** | `harness/*.c` | the solver build with inputs as free variables, so a SAT solver searches or proves. |

Everything else follows from that. `tests/diff.sh` is the load-bearing test:
40 random rooms × 300 random runs, both builds, every frame compared. If that
is green the solver build is trustworthy; if it is red nothing downstream
means anything.

**Data flow.** ASCII room (`rooms/*.txt`) → `celeste_sat/room_header.py`
(`tools/make_room.py`) → `room.h`, with the moving solids' paths precomputed
in single precision → `gcc` → `sim` / `beam` / `cbmc`. The state is passed
between rooms and into SAT queries as a generated C header (`START_STATE`),
written by `sim -s K out.h route.tas` and read by `celeste_sat/state.py`.

**Three implementations of the room transition** must agree:
`celeste_sat/transition.py` (`enter_room`, authoritative and documented),
`model/transition.h` (C, for `tools/cross.py`), and the game.
`tools/cross.py --check-transition` compares the first two (the test suite
runs it).

## Layout

```
model/          the port: celeste.h (State, Input, constants), celeste.c (everything else),
                state_eq.h (which states have the same future), transition.h (the room transition in C)
sim/            sim.c replays a route (and dumps states), chain.c two rooms in one program,
                live.c finds the state fields that no longer matter, tas_io.h reads/writes TAS files
search/         beam.c, the beam search: the only thing that finds long routes
harness/        CBMC entry points: solve.c (one room), window.c (a stretch of a route), cross.c (two rooms);
                input_rules.h (symmetry breaking and dominance on free inputs)
celeste_sat/    the Python library every script uses (see its __init__.py)
tools/          command lines: solve, windows, cross, chapter, chain_chapter2, celestetas, import_map, ...
tests/          checks with a pass/fail answer (tools/run_tests.sh runs them)
experiments/    the scripts behind specific findings (TAS endings, crossings, probes); need cbmc and time
hpc/            Slurm scripts for the cluster campaign
rooms/          demo rooms; rooms/vanilla/ for rooms exported from the game
data/recordings/  CelesteTAS ExportGameInfo recordings from the real game: the ground truth
results/        routes worth keeping (routes/), files to play them in the game (celestetas/), the replay page
game/           your own copies of the game's map files (not in git)
```

## Commands

```bash
bash tools/run_tests.sh                     # ~5 min on 2 cores, no game files or cbmc needed (CI runs this)
bash tools/run_tests.sh --vanilla --sat     # + Chapter 1 against the game, recordings, CBMC checks
python3 -m unittest discover -s tests -p "test_*.py"   # the Python unit tests alone
sh tests/diff.sh 40 300 400                 # the differential fuzzer alone
python3 tests/chain_tas.py                  # the community TAS through all of Chapter 1
python3 tools/solve.py rooms/ledge.txt --polish
python3 tools/windows.py rooms/vanilla/1a_lvl_1.txt build/chain_tas/lvl_1/route.tas \
    --width 8 --from 40 --to 45             # SAT on windows of a known route
python3 tools/chain_chapter2.py --polish    # the Chapter 2 chase, room by room
```

Toolchain: gcc (with OpenMP), Python 3, CBMC 5.95.1 (`apt install cbmc`;
MiniSat). On Windows use WSL. The scripts in `tools/`, `tests/` and
`experiments/` run from anywhere; each puts the repository root on
`sys.path` to import `celeste_sat`.

## Invariants -- do not break these

- **The two builds must stay bit-identical.** Any new mechanic needs a
  `tests/random_room.py` generator and a green `tests/diff.sh` run, with a
  coverage counter showing it fired, before it is believed. This is the
  whole epistemology of the project: two real Chapter 2 bugs lived through a
  "completed" 2,116-frame speedrun and fell out of the first fuzz run that
  covered them ([history.md](history.md#2026-10-04-chapter-2-into-the-verification-net)).
  When you add a generator, keep the RNG draws inside the new branch so the
  rooms for other seeds stay byte-identical and the existing coverage is
  preserved.
- **Every new live state field needs four edits**: `model/celeste.h` (the
  field), `model/state_eq.h` (`same_future`), `tests/fuzz.c` (`scramble`, if
  the field is one that cannot matter), and `sim/sim.c`'s `dump_state` if
  chaining depends on it. Miss `same_future` and proofs quietly weaken.
- **Every new field that a room transition clears needs two edits**:
  `celeste_sat/transition.py` (`enter_room`) and `model/transition.h`.
- **The include boundary.** `harness/cross.c` includes `celeste.h`, not
  `celeste.c`; anything `state_eq.h` or `transition.h` needs from a room's
  `room.h` must reach it through `cross_setup.h` (`tools/cross.py` copies the
  entity counts there). A missing macro there silently compiles a check away;
  `tools/cross.py --check-transition` on the chase rooms is the quick test.
- Keep float operations in C# order ([model.md](model.md#fidelity-details)
  explains why; it is not stylistic).
- **Model changes invalidate saved proofs and routes.** Record the commit
  every result was computed at, and re-run the replays after a model change
  (the Chapter 2 routes in `results/archive/` are what happens otherwise).
- **A route is not a result until it is played in the game.** A SAT "yes"
  or a faster beam route is a statement about the model.

## Adding a mechanic (an entity, a state)

1. A `; directive` in the room format (`celeste_sat/room.py`) and its export
   (`celeste_sat/celeste_map.py`) and `room.h` tables
   (`celeste_sat/room_header.py`);
2. the model code, with a coverage counter (`COV(...)` in `celeste.c`);
3. a **`tests/random_room.py` generator**;
4. a **green `tests/diff.sh` run**, with the coverage counter non-zero;
5. `same_future` + `scramble()` entries for any new live state;
6. `celeste_sat/transition.py` + `model/transition.h` entries for anything the
   transition clears;
7. an **in-game recording** that matches frame for frame.

Do not let a mechanic reach a route before step 4.

## Known warts

- `State` is 1,316 bytes, 1,024 of them the chaser history (`histX`/`histY`),
  in every room, because `celeste.h` cannot see `HAS_CHASER` (defined in the
  generated `room.h`, included later). The beam search copies whole states
  on its hot path, so non-chase rooms pay for it. Making it conditional is
  not free: `harness/cross.c` links two rooms that must share one `State`
  layout, and the history's length decides `chaserTimer` on entry into the
  next room (`carry_chaser_history`).
- The beam search's state hash (`hash_state` in `search/beam.c`) leaves the
  chaser history out, so two states that differ only in where Badeline will
  be are merged and one of them is dropped. Harmless for correctness (every
  route is replayed), but it weakens the search in chase rooms.
- `tools/windows.py` and `sim/live.c` know only the Chapter 1 state fields:
  the `SF_*` mask has no bits for the Chapter 2 ones, so they are always
  compared. Correct (stricter), not as fast as it could be.
- `harness/input_rules.h` has no `ST_DREAM_DASH` dominance rules: during a
  dream dash almost every input is a don't-care, which is free formula size
  if CBMC is ever pointed at a dream-block room.
- `tests/random_room.py` places a switch gate only when fewer than three zip
  movers are already there (they share `MAX_ZIP_MOVERS`), so check the
  coverage counters, not the seed, to know whether something was exercised.
- `tools/import_chapter2.py` names `lvl_d3` as the goal of `lvl_d8`, but
  `lvl_d3` itself is not exported.
