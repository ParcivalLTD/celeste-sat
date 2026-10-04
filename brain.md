# brain.md — orientation for continuing celeste-sat

Written 2026-10-04 against `main` @ `6455596`. The README is the project's
*public* document and it is excellent — read it for the model's contents, the
fidelity arguments and the measured results. **This file is the internal one**:
what shape the code is in, where the Chapter 1 work ended and the Chapter 2
work actually stands, and what to do next.

---

## 1. The one idea

One C port of Madeline's movement, compiled three ways:

| build | defined by | used for |
|---|---|---|
| **reference** | `-DREFERENCE` | literal float timers, pixel-by-pixel movement. The oracle. |
| **solver** | (default) | integer frame counters from `gen_tables.c`, boundary-jump movement, an 8×8-tile collision window. Must be bit-identical to the reference. |
| **CBMC harness** | `harness/*.c` | the solver build with inputs as free variables, so a SAT solver searches or proves. |

Everything else follows from that. `tests/diff.sh` is the load-bearing test:
40 random rooms × 300 random runs, both builds, every frame compared. If that
is green the solver build is trustworthy; if it is red nothing downstream means
anything.

**Data flow.** ASCII room → `tools/make_room.py` → `room.h` (+ precomputed zip
mover paths / falling block drops, replayed in single precision) → `gcc` →
`sim` / `beam` / `cbmc`. State is passed between rooms as a generated C header
(`START_STATE` in `entry.h`), written by `sim -s K out.h route.tas`.

**Three implementations of the room transition** that must agree:
`tools/chapter.py:enter_room` (Python, authoritative + documented),
`model/transition.h:enter_room` (C, for `tools/cross.py`), and the game.
`tools/cross.py` compares the first two and aborts on any disagreement.

---

## 2. Layout beyond the README's table

```
model/      the port (celeste.c is 2,579 lines and is the project)
sim/        replay (sim.c), two-room replay (chain.c), dead-field prober (live.c)
search/     beam.c — the only thing that finds long routes
harness/    CBMC entry points: solve.c (one room), cross.c (two), window.c (a stretch)
tools/      the pipelines; solve.py is the main one, chapter.py chains rooms
tests/      diff.sh is the important one; the rest check against the real game
rooms/      demo rooms + rooms/vanilla/ (exported from a real map file)
results/    committed routes and recordings worth keeping
recordings/ CelesteTAS ExportGameInfo dumps from the real game (572 KB)
```

`1-ForsakenCity.bin` in the repo root is a real Celeste map file, vendored so
`tests/chain_tas.py` works out of the box (it is the default `--map`). It is
game content — if this repo ever goes properly public, that is the first thing
to reconsider. `2-OldSite.bin` is *not* vendored, which is why the Chapter 2
room exports are committed under `rooms/vanilla/` instead.

---

## 3. Cheatsheet

```bash
bash tools/run_tests.sh                     # ~3 min, no cbmc needed
bash tools/run_tests.sh --vanilla --sat     # adds Chapter 1 rooms + CBMC checks
python3 tools/solve.py rooms/ledge.txt --beam-rollout 10
python3 tools/chain_chapter2.py --polish    # the Chapter 2 chase, room by room
python3 tests/test_chapter2.py              # dream blocks + chaser
```

Toolchain here: gcc 16.2.1, python 3.14.7, **cbmc not installed** (`sudo pacman
-S cbmc` / `apt install cbmc`). Everything that does not need CBMC runs clean.

Verified green on 2026-10-04: 40/40 fuzz rooms bit-identical, 2,046,706
symmetry checks and 6,972,868 `same_future` checks with 0 broken, all saved
routes replay to their recorded frame in both builds.

---

## 4. Where the work actually stands

### Chapter 1 — finished and genuinely verified

The whole community TAS (19 rooms, 2,275 frames) replays exactly, every room
leaving on its last input frame. Recordings from Celeste 1.4 match frame for
frame, subpixels included. Two SAT findings on the TAS's own routes, one
confirmed in the game (the 106-frame `lvl_3`). This part is done, and the
level of rigour is the standard the rest of the project should be held to.

### Chapter 2 — a working pipeline on an unverified model

Five commits on 2026-09-30 added dream blocks, a Badeline chaser, 128-tile-tall
room support, and an automated chase pipeline, ending in a 13-room /
2,116-frame / 35.27 s route (`results/2a_chase.tas`). The pipeline works. The
model underneath it has **not** been through any of the three checks that make
the Chapter 1 work believable:

1. it is not in the differential fuzzer,
2. it is not in `same_future`,
3. nothing has been recorded in the real game.

Concretely, and ranked:

**(a) The fuzzer does not generate dream blocks or a chaser.**
`tests/random_room.py` emits zip movers, falling blocks, crumbles, dash blocks,
springs, refills and spikes — no `; dreamblock`, no `; chaser`. So the
`ST_DREAM_DASH` code path and `chaser_update` have never been compared between
the reference and solver builds beyond the single hand-written route I added
(`tests/dream_test.tas`, 52 frames). Everything the README claims about
bit-identical builds is silent about Chapter 2. **This is the first thing to
fix** — it is also the cheapest, because `random_room.py` already has the shape
for it.

**(b) `same_future` ignores every Chapter 2 field.**
`model/state_eq.h` compares nothing of `dreamDashCanEndTimer`, `dreamJump`,
`chaserTimer`, `histX`, `histY`. `same_future` is what makes a "no" from
`tools/cross.py` and `tools/windows.py` a *proof*: it is the claim "these two
states have the same future". On a Chapter 2 room that claim is now false, and
nothing fails loudly — the query just answers a weaker question than it
reports. Either add the fields (and the matching `scramble()` cases in
`tests/fuzz.c`, which is how the Chapter 1 fields earned their place) or make
the cross/window tools refuse rooms with `NDREAMBLOCKS > 0 || HAS_CHASER`.
The unmerged branch adds `tsOn` to `same_future` but still not these.

**(c) `model/transition.h` does not reset what `tools/chapter.py` resets.**
The Python `enter_room` zeroes `dreamDashCanEndTimer`, `dreamJump` and
`chaserTimer`; the C one zeroes `tsOn` (on the branch) but none of those three.
Its own header comment says the two are the same rules. This one *is*
fail-loud — `tools/cross.py` diffs the two entry states and aborts — so the
practical effect is that `cross.py` cannot run on any chase room at all
(`chaserTimer` is nonzero after every room). Fix the C side to match.

**(d) The chaser is a placeholder, not Badeline.**
`chaser_update` (`model/celeste.c:2098`) records her position every frame and
kills her if she is ever inside an 8×11 box at *where she herself was
`CHASER_DELAY` frames ago*. It is a ghost retracing her exact path on a delay
— no path nodes, no acceleration, no line of sight. The real
`BadelineOldsite` chases with its own movement. The history is also reset per
room, so in the chained chase Badeline restarts behind her in every room.
The unmerged branch is titled "Badeline as in the game", which means the
2,116-frame result is provisional: it was found against a chaser that is easier
to escape than the real one.

**(e) Unmodelled solids in the chase rooms.**
`invisibleBarrier` is listed as NOT MODELLED in `2a_lvl_2`, `2a_lvl_9` and
`2a_lvl_10` — those are *solid* in the game, so a route through those rooms can
walk through a wall that really exists. `switchGate` (4 rooms) and
`touchSwitch` (4 rooms) likewise. `2a_lvl_10` taking 482 frames and `2a_lvl_13`
taking 5 are both worth a sanity look for exactly this reason. The unmerged
branch adds switch gates and touch switches; invisible barriers are easy
(static solids) and should just be done.

### The unmerged branch is the actual continuation

`origin/claude/chapter2-ingame`, 2 commits, +1759/−509 across 23 files:
switch gates, touch switches, "Badeline as in the game", `CHASER_HIST_LEN`
128 → 256, `results/celestetas/2a_chase.tas` (an in-game test file), README
+54 lines. **Read this branch before writing any new Chapter 2 code** — most
of what looks missing on `main` is sitting there. Deciding whether to merge it
or rebuild on top of it is the first real decision.

---

## 5. Two concrete regressions found while reading

**`--beam-rollout` defaults to 8 in `solve.py` but 10 inside `beam.c`.**
Both have been that way since the first commit, and the README's demo numbers
are the `beam.c` ones. Through the documented pipeline you get worse routes
than the README reports, and the project's own test suite prints the gap:

| room | `run_tests.sh` (rollout 8) | rollout 10 | saved `results/*.tas` | README |
|---|---|---|---|---|
| `ledge` | 19 | **17** | 18 | 18 |
| `hop` | 23 | 21 | 21 | 21 |

Rollout is not monotone (ledge: 19 at r=8, 18 at r=6, **17** at r=10, 18 at
r=12), and on `2a_lvl_3` r=8 wins 102 to 103, so it is room-dependent rather
than a uniform bug. But the default should at least match `beam.c`'s, and
`--beam-rollout` deserves a sweep rather than a guess.

**There is a 17-frame `ledge` route.** Found at rollout 10, verified in both
builds (`1,L,X` / `3` / `1,R,U,J` / `2,R,J` / `2,L,J` / `1,R,J` / `1,R,K,G` /
`1,K` / `1` / `3,R` / `1,L`). It does not contradict anything the README
actually claims — the only full-model proof there is "frames 1–8 fixed", and
this route diverges at frame 5 — but `results/ledge.tas` is no longer the best
known route for the project's flagship demo room, and the `ledge` row in
"Results (demo rooms)" is stale. Worth re-running the SAT descent on once
cbmc is installed; it is the cheapest proof in the repo.

**`sizeof(State)` went from ~300 to 804 bytes**, 512 of which is
`histX`/`histY` — present in *every* room, chaser or not, because `celeste.h`
cannot see `HAS_CHASER` (it is defined in the generated `room.h`, included
later by `celeste.c`). `search/beam.c` mallocs `2 × sizeof(State) × beam_width`
and copies whole States on its hot path, so a room that fills a 100k beam now
holds ~153 MB of buffers instead of ~56 MB. I measured no wall-clock
difference on `ledge` (too small to fill the beam), so treat this as a
scaling concern for the long chase rooms, not a proven slowdown. CBMC should be
unaffected — with `HAS_CHASER` 0 the arrays are never written and get sliced
away.

---

## 6. Invariants — do not break these

- **The two builds must stay bit-identical.** Any new mechanic needs a
  `random_room.py` generator and a `tests/diff.sh` run before it is believed.
  This is the whole epistemology of the project.
- **Every new live state field needs three edits**, not one: `celeste.h`
  (the field), `state_eq.h` (`same_future`), and `fuzz.c` (`scramble`, if the
  field is one that cannot matter). Miss the second and proofs quietly weaken.
  Chapter 2 missed it.
- **Every new field that a room transition clears needs two edits**:
  `tools/chapter.py:enter_room` *and* `model/transition.h:enter_room`.
- **`sim -s` must dump any field that chaining depends on.** It currently
  dumps `dreamDashCanEndTimer`, `dreamJump` and `chaserTimer` but not
  `histX`/`histY`, which is fine only while the chaser resets per room.
- Keep float operations in C# order. The README's fidelity section explains
  why; it is not stylistic.
- Model changes invalidate saved proofs. The README is careful to label which
  model each result came from — keep doing that.

## 7. Known warts (cosmetic, safe to leave)

- `tools/make_room.py:parse()` returns six values and smuggles five more out as
  function attributes (`parse.fallblocks`, `parse.crumbles`, `parse.dashblocks`,
  `parse.dreamblocks`, `parse.chaser`). Pre-dates Chapter 2; wants a dataclass.
- `make_room.py` asserts `len(dreamblocks) <= 8` with a literal instead of
  `MAX_DREAM_BLOCKS`.
- `tools/import_chapter2.py` lists `lvl_d8 -> lvl_d3`, but `lvl_d3` is not in
  its own room list and `2a_lvl_d3.txt` does not exist.
- `harness/input_rules.h` has no `ST_DREAM_DASH` dominance rules — during a
  dream dash almost every input is a don't-care, which is free formula size if
  CBMC is ever pointed at a dream-block room.

---

## 8. Suggested order of work

1. **Install cbmc.** Half the project is unreachable without it.
2. **Read `origin/claude/chapter2-ingame`** and decide: merge, or cherry-pick
   the real Badeline onto `main`.
3. **Dream blocks and a chaser in `random_room.py`**, then `tests/diff.sh`.
   Until this is green, every Chapter 2 number is provisional.
4. **Chapter 2 fields into `same_future` + `scramble`**, and
   `model/transition.h` into line with `chapter.py`.
5. **Record something from Chapter 2 in the real game** with
   `tools/celestetas.py` — the branch already has
   `results/celestetas/2a_chase.tas`. One recording would settle the dream
   block's timing the way the `lvl_4` recording settled falling-unduck.
6. **Invisible barriers** (static solids, ~an hour) so the chase rooms stop
   being optimistic.
7. Then the interesting part: the beam search is the real bottleneck (the
   README is honest that it is "well behind the TAS" — 99 vs 92 on room 1
   because the rollout never dashes or wall-boosts on its own). The README's
   "Ideas for going further" section is a good list; the rollout policy is the
   highest-leverage item on it.

---

## 9. Cleanup already applied on 2026-10-04

- `.gitignore`: `build/` and `rooms/vanilla/` were ignored while 21 files
  inside them were tracked. The chase TAS moved
  `build/chapter2_chase/2A_chase.tas` → `results/2a_chase.tas`, and the
  Chapter 2 room exports are now explicitly un-ignored with a comment saying
  why they are committed.
- `tools/chain_chapter2.py`: the room-transition block was duplicated verbatim
  twice and `--from` was parsed but never used. Factored into `write_entry()` /
  `solve_room()`, `--from` implemented (and it now errors instead of silently
  re-solving when an earlier room has no route), `import re` hoisted, dead
  beam-width guards dropped. ~160 lines, same behaviour.
- `tests/test_chapter2.py`: rewritten to the project's style; the per-test
  rebuild deduplicated into `build()`; the chaser tests now read `death_frame`
  from the json trace instead of grepping stdout for a string the simulator
  never printed — test 4 was passing for the wrong reason.
- `sim/sim.c`: a run that ended in death printed `died at frame N` and then
  `no exit within N frames` as its *last* line, so anything reading the last
  line saw no death. It now says `no exit: died at frame N`.
- `tools/run_tests.sh`: ran none of the Chapter 2 code. Added the mechanics
  tests and a `tests/dream_test.tas` replay through both builds.
