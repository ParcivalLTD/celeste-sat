# History

A lab notebook: what was done, what was found, and why, newest first. The
README and the other docs describe the project as it is; this is how it got
there. Entries before 2026-10-12 come from `brain.md`, the working notes of
the time, and describe the code as it was then (file names included).

## 2026-10-12: cleanup, and an audit of the claims

The repository was restructured (see the commit for the full list): a Python
library (`celeste_sat/`) instead of scripts importing each other through
`sys.path`; `tests/` (pass/fail checks) separated from `experiments/` (the
scripts behind particular findings); recordings from the game in
`data/recordings/`; routes in `results/routes/`; the README split into
`docs/`; the game's map file and the community TAS no longer in the
repository (the tools read the map from `game/` and download the TAS at a
pinned commit). Every refactored tool was checked against the code before
it: `room.h` byte-identical for 128 rooms (demo, all of Chapter 1 and 2, 80
random), room exports byte-identical, the community TAS chain, the fuzzer,
the recordings and the CBMC checks giving the same answers.

What the audit found, beyond the code:

- **`recordings/1A_improved.tas` was the community TAS.** The fix of 588c008
  restored the community `lvl_6a`/`lvl_6b`, which made the file
  byte-for-byte VampireFlower's `1A.tas` at the pinned commit. (The replaced
  `lvl_6a` was the 118-frame sweep route. It does replay from the TAS's entry
  into the room, x = 4, contrary to the diagnosis at the time. The in-game
  test file `test_6a_6b_improved.tas` started it with `console load 1
  lvl_6a`, which puts her at the room's spawn, so that test could not have
  worked; see results.md.) Its in-game time, 0:49.079 (2,887 frames), is the
  community TAS's own `ChapterTime`. No improved Chapter 1 route has been
  played in the game yet; the Leonardo campaign's 15 model-only frames are
  still to be assembled into one and recorded.
- **2,275 frames is not a chapter time.** It is the community TAS's frames of
  control inside the rooms; the chapter time is 0:49.079.
- **The committed Chapter 2 routes did not replay** in the model of commit
  588c008 (both died or stalled in `2a_lvl_6`). The cause was the
  touch-switch change below; with it reverted, both replay exactly again.
- **`ledge` has a 17-frame route** in the full model (brain.md had found it;
  now `results/routes/ledge_17.tas`), so the README's "18 is optimal" holds
  only for the first model.
- **The touch-switch hitbox change of 1d3e148 was reverted.** It replaced the
  switch's 30 × 30 `PlayerCollider` against her hurtbox with the 16 × 16
  entity `Collider` against her collider. The published `Player.cs` (the
  hurtbox swap around the `PlayerCollider` loop) and a mod that mirrors the
  vanilla switch (MaxHelpingHand's `FlagTouchSwitch`) both support the
  original. The change was made because the beam search could not get
  through `2a_lvl_7`, but a 252-frame route through that room under the
  original hitbox was already committed (`results/routes/2a_chase.tas`). A
  room the search can't solve is a search problem, not a reason to change
  the model. See [verification.md](verification.md#chapter-2-nothing-recorded-yet).
- `tools/import_chapter2.py` would have silently undone the exit fixes of
  588c008 on the next re-export; they are now part of it (`EXIT_FIXES`).
- The beam search's default rollout was 10 in `beam.c` and 8 in
  `tools/solve.py`; both are 8 now (every recent result used 8). It is not
  uniformly best -- sweep it.

## 2026-10-05 to 10-12: the Leonardo campaign

About 2,300 core-hours on CINECA Leonardo's Booster partition (`hpc/`), as
reported when access ended on 2026-10-12:

- window proofs over the chained community TAS: W = 12 over all 19 rooms
  (71 chunks, 1,935 windows), W = 16 over all 19 (81 chunks, 1,842 windows),
  W = 18 over `lvl_1` (73 windows); 4,371 queries, 4,338 "no", the rest
  timeouts;
- "faster" windows (model only) in `lvl_6a` (−5 frames), `lvl_12` (−5),
  `lvl_9b` (−3) and `lvl_3b` (−2);
- the Chapter 2 chase at beam width 500,000 on 32 cores: rooms 3-9 solved
  (105, 117, 141, 222, 245, 207, 102 frames), `2a_lvl_10` failed at frame 55
  because the `2a_lvl_9` exit let her leave at x = 257 into rock (fixed in
  588c008 by narrowing the exits).

The output was committed on 2026-10-13 (`results/leonardo/`). Read with
`hpc/summary.py`, all 15 "faster" windows turned out to be faster room
*endings* in a different exit state, none of them a chapter saving (results.md).



## 2026-10-04: invisible barriers and the entity census

**`tools/entity_census.py`.** ROADMAP §4.1 said to write this before guessing
at the backlog. It exports every room with `tools/import_map.py` and reads the
`; NOT MODELLED (ignored)` line out of the result, so it cannot drift from what
the exporter actually supports. `--tas` marks the rooms a community TAS visits,
which is the distinction that decides whether an entity blocks a chapter or
just sits in a side room.

Chapter 1: **34/38 rooms fully modelled, 20/20 on the TAS route, nothing
blocking.** The four gaps are all off-route: `cassetteBlock` + `cassette` in
`lvl_11z`, `birdForsakenCityGem` in `lvl_s1`, `npc` in `lvl_6zb`,
`coverupWall` in `lvl_7a`. Only `cassetteBlock` is a real mechanic; the rest
are collectables and scenery that probably belong in `import_map.py`'s
`COSMETIC` set, but each is a fidelity claim, so they are left alone.

Run it over the whole game before starting any Chapter 3+ work:

```bash
python3 tools/entity_census.py "<Celeste>/Content/Maps" --json census.json
```

**Invisible barriers.** `InvisibleBarrier` is a `Solid` that never moves and is
never drawn. Because it is static it needs **nothing** in `State`, in
`same_future` or in the transition — only a box among the moving solids
(`MS_BA0`, after the dream blocks), after which every existing solid check sees
it, including `first_solid_at`'s tiles-then-entities ordering and the climb-hop
solid tracking. That is why it was an hour's work and not a day's.

Two things worth remembering from doing it:

- **A barrier over solid tiles is invisible to the fuzzer.** `collide_box` is
  `tiles_collide || any_ms_overlap`, which short-circuits, so a barrier behind
  a wall can never block anything. The generator has to place them in open air
  or the coverage counter stays at 0 — which is exactly what happened on the
  first two attempts. Half of them are placed off the tile grid, since nothing
  requires alignment and the model must not assume it.
- **One room's counter being 0 proves nothing.** Seed 3 reads as a total
  failure (0 barrier hits) because that particular random room walls her into
  the spawn column — `x 12..12` for all 120,000 frames. Across 40 rooms the
  same code blocks her 51,456 times. Check the aggregate, never a single room.

Also fixed while in there: `same_future` guarded the climb-hop solid
(`hopZip`) on only the first four moving-solid kinds, while the code that sets
it is guarded on `NMS > 0`. A room with *only* dream blocks, or only barriers,
would therefore have left `hopZip` out of the comparison. Pre-existing, latent
since dream blocks landed.

**Still to do for this item:** the three Chapter 2 rooms that contain barriers
were exported before the model supported them, so they must be re-exported
from `2-OldSite.bin` (§4b). The model side is fuzz-verified; the room files are
not yet updated, and that is the part a fresh clone cannot do for itself.

## 2026-10-04: Chapter 2 into the verification net

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

---

## 2026-10-04: repository hygiene

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

## 2026-10-04: where Chapter 1 and Chapter 2 stood

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

1. ~~it is not in the differential fuzzer~~ — **done** (the Chapter 2 entry below), and it found two
   real bugs straight away;
2. ~~it is not in `same_future`~~ — **done** (the Chapter 2 entry below);
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

**(b) Unmodelled solids in the chase rooms — modelled, not yet re-exported.**
`invisibleBarrier` is now in the model (the invisible-barrier entry) and in the fuzzer. But
`rooms/vanilla/2a_lvl_2.txt`, `2a_lvl_9.txt` and `2a_lvl_10.txt` were exported
*before* that, so they still carry `; NOT MODELLED (ignored): invisibleBarrier`
and no `; barrier` lines. **Until they are re-exported those three rooms still
let a route walk through walls that exist**, which needs `2-OldSite.bin` (not in
the repo):

```bash
python3 tools/import_chapter2.py          # re-exports every 2a_*.txt
python3 tools/entity_census.py 2-OldSite.bin    # invisibleBarrier should be gone
```

`2a_lvl_10` taking 482 frames and `2a_lvl_13` taking 5 are both worth a sanity
look once that is done — they are the rooms most likely to have been exploiting
a missing wall.

**(c) The chase route is provisional.** `results/2a_chase.tas` (13 rooms, 2,116
frames) was found before the merge and before the two model fixes in the Chapter 2 entry below. It
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

### Three things found while reading

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
builds and still 17 after the the Chapter 2 entry below model fixes (`1,L,X` / `3` / `1,R,U,J` / `2,R,J` / `2,L,J` / `1,R,J` / `1,R,K,G` /
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
