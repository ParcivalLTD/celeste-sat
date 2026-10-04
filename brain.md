# brain.md — orientation for continuing celeste-sat

Written 2026-10-04, on `brain-and-cleanup` (= `main` + `claude/chapter2-ingame`
merged + the work in §9/§10). The README is the project's *public* document and
it is excellent — read it for the model's contents, the fidelity arguments and
the measured results. **This file is the internal one**: what shape the code is
in, where the Chapter 1 work ended and the Chapter 2 work actually stands, and
what to do next.

> **Status 2026-10-04.** `claude/chapter2-ingame` is merged. Chapter 2 is now in
> the differential fuzzer, which immediately found two real model bugs (§10).
> Both are fixed; 40/40 rooms are bit-identical again. Next up is a Chapter 2
> recording from the real game, and invisible barriers.

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
sh tests/diff.sh 40 300 400                 # the load-bearing test, ~4 min
```

Toolchain here: gcc 16.2.1, python 3.14.7, **cbmc not installed** (`sudo pacman
-S cbmc` / `apt install cbmc`). Everything that does not need CBMC runs clean.

Verified green on 2026-10-04 (after the merge and the §10 work): 40/40 fuzz
rooms bit-identical over 2.88 M frames, 1,919,466 symmetry checks and 6,621,038
`same_future` checks with 0 broken, every Chapter 2 mechanic exercised, all
saved routes replaying to their recorded frame in both builds, and the C
transition agreeing with the Python one.

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
model underneath it had **not** been through any of the three checks that make
the Chapter 1 work believable. Two of the three are now closed:

1. ~~it is not in the differential fuzzer~~ — **done** (§10), and it found two
   real bugs straight away;
2. ~~it is not in `same_future`~~ — **done** (§10);
3. **nothing has been recorded in the real game** — still open, and now the
   most valuable thing left to do.

What remains:

**(a) No Chapter 2 recording from the real game.** Every Chapter 1 fidelity
claim rests on CelesteTAS recordings; Chapter 2 has none. The merged branch
ships `results/celestetas/2a_chase.tas` ready to play, and
`tests/recordings.py` will check it room by room. Until that is done, the dream
block's `DREAM_DASH_MIN_TIME`, the chaser's 1.55 s delay and its 6x6 hitbox are
all inferred. One recording would settle them the way the `lvl_4` recording
settled falling-unduck.

**(b) Unmodelled solids in the chase rooms.**
`invisibleBarrier` is listed as NOT MODELLED in `2a_lvl_2`, `2a_lvl_9` and
`2a_lvl_10` — those are *solid* in the game, so a route through those rooms can
walk through a wall that really exists. `2a_lvl_10` taking 482 frames and
`2a_lvl_13` taking 5 are both worth a sanity look for exactly this reason.
Switch gates and touch switches came with the merge; invisible barriers are
static solids and should just be done.

**(c) The chase route is provisional.** `results/2a_chase.tas` (13 rooms, 2,116
frames) was found before the merge and before the two model fixes in §10. It
has not been re-derived since, and the merge replaced the chaser wholesale with
a much harder one. Treat the number as a placeholder until
`tools/chain_chapter2.py` has been re-run.

### The merged branch, and what it brought

`origin/claude/chapter2-ingame` (2 commits, +1759/−509 across 23 files) is
**merged** into `brain-and-cleanup`. It brought switch gates, touch switches,
`CHASER_HIST_LEN` 128 → 256, `SPAWN_FACING`, `results/celestetas/2a_chase.tas`
(an in-game test file) and, most importantly, a real Badeline:

`chaser_update` now follows `Player.ChaserStates` as the game does — chaser *i*
reads the position she recorded `CHASER_DELAY + 24 * i` frames ago (1.55 s plus
0.4 s per chaser behind), with a 6x6 hitbox at (-3, -7) against her hurtbox, a
`CHASER_WAKE` delay after `Player.JustRespawned` clears, and a history that
**runs on across rooms** (`carry_chaser_history` in `tools/chapter.py` carries
it, with 40 transition frames standing at the entry position). `main`'s version
was a ghost retracing her path with an 8x11 box, reset every room — strictly
easier to escape. Anything measured against `main`'s chaser is void.

Conflicts resolved in the merge, for the record: `.gitignore` took both sides;
`tools/chain_chapter2.py` took the branch's wholesale (its `solved_from.h`
cache validation is correct where the cleanup's "reuse any route that exits"
was not — a cached route from a different entry state is invalid);
`tests/test_chapter2.py` kept the cleanup's structure and took the branch's
test semantics.

---

## 5. Three things found while reading, still open

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
builds and still 17 after the §10 model fixes (`1,L,X` / `3` / `1,R,U,J` / `2,R,J` / `2,L,J` / `1,R,J` / `1,R,K,G` /
`1,K` / `1` / `3,R` / `1,L`). It does not contradict anything the README
actually claims — the only full-model proof there is "frames 1–8 fixed", and
this route diverges at frame 5 — but `results/ledge.tas` is no longer the best
known route for the project's flagship demo room, and the `ledge` row in
"Results (demo rooms)" is stale. Worth re-running the SAT descent on once
cbmc is installed; it is the cheapest proof in the repo.

**`sizeof(State)` is 1,316 bytes, 1,024 of it the chaser history**
(`histX`/`histY`, 256 shorts each after the merge raised `CHASER_HIST_LEN`) —
present in *every* room, chaser or not, because `celeste.h` cannot see
`HAS_CHASER`, which is defined in the generated `room.h` and included later by
`celeste.c`. Without it a State is 292 bytes, so this is a 4.5x inflation.
`search/beam.c` mallocs `2 * sizeof(State) * beam_width` and copies whole
States on its hot path, so a room that fills a 100k beam holds ~263 MB of
buffers instead of ~58 MB. I measured no wall-clock difference on `ledge` (far
too small to fill the beam), so treat it as a scaling concern for the long
chase rooms rather than a proven slowdown — but `2a_lvl_10` already needs 482
frames, and the adaptive beam-width fallback in `chain_chapter2.py` exists
precisely because those rooms are at the edge. CBMC should be unaffected: with
`HAS_CHASER` 0 the arrays are never written and get sliced away.

---

## 6. Invariants — do not break these

- **The two builds must stay bit-identical.** Any new mechanic needs a
  `random_room.py` generator and a `tests/diff.sh` run before it is believed.
  This is the whole epistemology of the project, and §10 is what happens when
  it is skipped: two real bugs lived through a "completed" 2,116-frame speedrun
  and fell out of the first fuzz run that covered them. When you add a
  generator, keep the RNG draws inside the new branch so the rooms for other
  seeds stay byte-identical and the existing coverage is preserved.
- **Every new live state field needs four edits**, not one: `celeste.h` (the
  field), `state_eq.h` (`same_future`), `fuzz.c` (`scramble`, if the field is
  one that cannot matter), and `sim/sim.c`'s `dump_state` if chaining depends
  on it. Miss `same_future` and proofs quietly weaken -- Chapter 2 missed it,
  see §10.
- **Every new field that a room transition clears needs two edits**:
  `tools/chapter.py:enter_room` *and* `model/transition.h:enter_room`.
- **`sim -s` must dump any field that chaining depends on.** It now dumps the
  dream fields, `chaserTimer` *and* `histX`/`histY` -- the last two matter
  because the merged chaser's history runs on across rooms.
- Keep float operations in C# order. The README's fidelity section explains
  why; it is not stylistic.
- Model changes invalidate saved proofs. The README is careful to label which
  model each result came from — keep doing that.

## 7. Known warts (cosmetic, safe to leave)

- `tools/make_room.py:parse()` returns six values and smuggles eight more out as
  function attributes (`parse.fallblocks`, `parse.crumbles`, `parse.dashblocks`,
  `parse.dreamblocks`, `parse.chaser`, `parse.nchasers`, `parse.zipkinds`,
  `parse.facing`). Pre-dates Chapter 2, and every new entity makes it worse;
  wants a dataclass.
- `make_room.py` asserts `len(dreamblocks) <= 8` with a literal instead of
  `MAX_DREAM_BLOCKS`.
- `tools/import_chapter2.py` lists `lvl_d8 -> lvl_d3`, but `lvl_d3` is not in
  its own room list and `2a_lvl_d3.txt` does not exist.
- `tests/random_room.py` places a switch gate only when fewer than three zip
  movers are already there (they share `MAX_ZIP_MOVERS`), and gives up on a
  room if 60 tries find no free box. So the gate rooms are a handful of the 40
  rather than a fixed sixth; check the coverage counters, not the residue
  class, when you want to know whether something was exercised.
- `harness/input_rules.h` has no `ST_DREAM_DASH` dominance rules — during a
  dream dash almost every input is a don't-care, which is free formula size if
  CBMC is ever pointed at a dream-block room.

---

## 8. Suggested order of work

Steps 2-4 of the original list are done (§4, §10). What is left, in order:

1. **Install cbmc.** Half the project is still unreachable without it
   (`pacman -S cbmc` / `apt install cbmc`). Everything else below can wait on
   this; nothing above it did.
2. **Record the Chapter 2 chase in the real game.** The file is ready:
   `results/celestetas/2a_chase.tas`, played in Celeste Studio, then
   `python3 tests/recordings.py <the Celeste folder>` checks it room by room
   and prints the first frame that differs. This is the one remaining leg of
   the three-way check, and the only way to settle the dream block's timing,
   the chaser's 1.55 s delay and its 6x6 hitbox. Note the route itself is
   provisional (§4c) -- but the recording checks the *model*, frame by frame,
   whether or not the route is optimal, so it is worth doing first.
3. **Invisible barriers** (static solids, ~an hour), so `2a_lvl_2`, `2a_lvl_9`
   and `2a_lvl_10` stop being optimistic.
4. **Re-run `tools/chain_chapter2.py`** to get a chase route that reflects the
   merged model and the §10 fixes, and replace `results/2a_chase.tas`.
5. **Fix the `--beam-rollout` default** (§5) and sweep it. Cheap, and it makes
   the README's demo numbers reproducible through the documented pipeline
   again.
6. **Re-run the SAT descent on `ledge`** once cbmc is there: there is a
   17-frame route (§5) and the saved one is 18, so the demo room's headline
   result is stale. It is the cheapest proof in the repo.
7. Then the interesting part: the beam search is the real bottleneck (the
   README is honest that it is "well behind the TAS" -- 99 vs 92 on room 1,
   because the rollout never dashes or wall-boosts on its own). The README's
   "Ideas for going further" is a good list; the rollout policy is the
   highest-leverage item on it.

Two things to keep in mind while doing any of it:

- `State` is 1,316 bytes, 1,024 of which is the chaser history, in *every*
  room (§5). `search/beam.c` mallocs `2 * sizeof(State) * beam_width` and
  copies whole States on its hot path. If the long chase rooms start thrashing,
  that is the first thing to look at -- it needs `celeste.h` to be able to see
  `HAS_CHASER`, which today is defined in the generated `room.h` and included
  later.
- `tools/windows.py` and `sim/live.c` are still entirely Chapter-1-only: the
  `SF_*` mask has no bits for the Chapter 2 fields, so `live.c` cannot probe
  them and `windows.py` always compares them. That is the safe direction (it
  can only make a window query stricter), so it is correct but conservative.

## 9. Cleanup applied on 2026-10-04

- `.gitignore`: `build/` and `rooms/vanilla/` were ignored while 21 files
  inside them were tracked. The chase TAS moved
  `build/chapter2_chase/2A_chase.tas` → `results/2a_chase.tas`, and the
  Chapter 2 room exports are now explicitly un-ignored with a comment saying
  why they are committed.
- `tests/test_chapter2.py`: rewritten to the project's style; the per-test
  rebuild deduplicated into `build()`; the chaser tests now read `death_frame`
  from the json trace instead of grepping stdout for a string the simulator
  never printed — the outrun test was passing for the wrong reason.
- `sim/sim.c`: a run that ended in death printed `died at frame N` and then
  `no exit within N frames` as its *last* line, so anything reading the last
  line saw no death. It now says `no exit: died at frame N`.
- `tools/run_tests.sh`: ran none of the Chapter 2 code. Added the mechanics
  tests and a `tests/dream_test.tas` replay through both builds.
- `tools/chain_chapter2.py` was tidied, then superseded by the branch's version
  in the merge (see §4).

## 10. Chapter 2 into the verification net — 2026-10-04

This is the work §8 lists as steps 3 and 4. It is done, and it paid for itself
immediately.

**`tests/random_room.py` now generates dream blocks and chasers.** Dream blocks
on `seed % 4 == 1` (so they meet both the zip movers of the even rooms and the
falling blocks of the odd ones), 1–3 per room; a chaser on `seed % 5 == 1`, one
or two of them, delay 60–120 frames. The new code only consumes RNG inside its
own branches, so the rooms for the other seeds are byte-identical to before and
the existing coverage is unchanged — worth preserving if you add more entities.

**`same_future` now compares the Chapter 2 state**, with the two claims that
make it cheap:

- `dreamDashCanEndTimer` and `dreamJump` are live only in `ST_DREAM_DASH`
  (both are set by `dream_dash_begin`, and `dreamJump` is read only inside
  `dream_dash_end`), so they are compared only in that state — the same shape
  as `dashStartedOnGround` in `ST_DASH`.
- Of the 256-entry chaser history, only the entries inside the longest chase
  delay (`SF_CHASER_MAX_DELAY = CHASER_DELAY + 24 * (NCHASERS - 1)`) can ever
  be read again, so only those and `chaserTimer` are compared.

`tests/fuzz.c`'s `scramble()` now scrambles exactly the fields those claims
declare dead — the dream fields outside `ST_DREAM_DASH`, and the history
entries past the longest delay — so the fuzzer *tests* the reasoning rather
than taking it on trust. That is how the Chapter 1 fields earned their place.

**`model/transition.h` now mirrors `tools/chapter.py`'s chaser carry-over**
(`carry_chaser_history`): the old room's history in the new room's coordinates,
then `TR_TRANSITION_GAP` frames at the entry position, `chaserTimer = n`. It
also clears the two dream fields. Before this the C and Python `enter_room`
disagreed on any chase room, which `tools/cross.py` would have caught loudly —
so it was blocking rather than silent, but it blocked everything.

`rooms/chase_a.txt` and `chase_b.txt` are the stacked demo rooms with a chaser
added, and `tools/run_tests.sh` runs `tools/cross.py --check-transition` on
them. That is the only thing that exercises the carry-over branch, and it needs
no cbmc. Keep it in the default suite.

**`tools/cross.py` now passes room B's entity counts to the harness.** This was
a pre-existing hole, not a Chapter 2 one: `harness/cross.c` includes
`celeste.h`, not `celeste.c`, so `NZIPMOVERS`, `NDREAMBLOCKS`, `HAS_CHASER` and
friends were *undefined* there — and every `#if N... > 0` block of
`same_future` compiled out silently. A cross-room "no" was a claim about a
weaker equivalence than it reported, for zip movers as much as for dream
blocks. It was latent only because no cross-room query has yet been run on a
room with entities. The counts are now copied out of the generated `room_b.h`
into `cross_setup.h`, so they cannot drift from what the model was built with.
`--check-transition` runs the C-vs-Python transition check and stops, which
needs no cbmc.

**This include boundary will bite again.** Anything `state_eq.h` or
`transition.h` needs that is defined in `celeste.c` is invisible to
`harness/cross.c`. It caught `CHASER_MAX_DELAY` within minutes of my adding it,
and the fix was a `#ifndef` fallback in `state_eq.h` fed by `cross_setup.h`.
When you add a macro those headers depend on, check that cross.c still builds —
`tools/cross.py --check-transition` on the chase rooms is the quick way, and a
failure here is a compile error, not a wrong answer.

**Coverage counters** for the nine new paths, so `tests/diff.sh`'s "mechanics
exercised" table shows the Chapter 2 model is actually being exercised rather
than merely compiled. Switch gates and touch switches needed a generator too
(a gate only fits when a `MAX_ZIP_MOVERS` slot is free, and a gate with no
switch would never open, so the generator drops one without the other). After
all of it, on 40 rooms x 300 runs:

```
rooms identical           40/40        2.88 M frames compared
symmetry rules            1,919,466 checks, 0 broken
same_future               6,621,038 checks, 0 broken
dream block entered       437     ... ended in a solid: 102 wiggled out, 171 fatal
dream block left          254     ... 92 with a jump, 6 into a climb
touch switch hit          991     switch gate opens 421
caught by a chaser        1,307
```

The two numbers that matter most are the 171 and the 102: those are the exact
paths of the two bugs below, and before this run nothing had ever executed
them in both builds.

### The two bugs the fuzzer found

Both were in the frame a dream dash ends, both made the solver build and the
literal reference build disagree, and both are fixed.

**1. A dead player kept moving.** `dream_dash_update` sets `dead` and returns
`ST_NORMAL` when the dash ends inside a solid, but `player_update` then ran the
ordinary movement block anyway. She is inside a solid at that point, which
violates the precondition of the solver build's boundary-jump movement (it
assumes she starts outside solids), so the two builds moved her differently —
4 rooms of 40. In the game `Player.Die` ends the update, so `player_update` now
returns when `dead` is set by the state machine. Worth knowing: that early
return is reachable only from this one path, because every other `dead = true`
in the model (spikes, bounds, squish, chaser) already runs after the movement.

**2. The dream-dash wiggle could leave her inside a dream block.**
`dream_dashed_into_solid` searched ±5 px for a spot free of solids using a
check that deliberately excluded dream blocks, so it could place her *inside*
one. She then stood inside a solid in `ST_NORMAL`, and the next move diverged
between the builds. The game's `DreamDashedIntoSolid` uses plain
`CollideCheck<Solid>`, and a `DreamBlock` **is** a `Solid`, so the exclusion
was simply wrong; the model now uses `collide_at`. The first check is
unaffected (it only runs when she is outside every dream block), so this
changes only where the wiggle may put her.

The first bug only ever showed up on a frame she died on, so it invalidates no
route. The second one does change behaviour on a surviving path, which is
another reason to treat `results/2a_chase.tas` as provisional.

The moral is the one §6 already states: **a mechanic outside the differential
fuzzer is not known to work.** Both bugs had been sitting in `main` since the
Chapter 2 commits, through a 2,116-frame "completed" speedrun, and the fuzzer
found them in one run.
