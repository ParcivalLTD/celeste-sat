# Roadmap

The plan. For the current state and the next concrete steps, with commands,
see [brain.md](brain.md).

Three goals, in the order the work can deliver them:

1. **A new TAS record** for a Celeste chapter, played in the real game.
2. **A paper**: a frame-exact model of a commercial platformer, SAT proofs
   about speedrun routes, and improvements to a human world-record TAS.
3. **A project that reads well on a CV**: public, reproducible, honest about
   what it shows.

They are the same work. Goal 1 gives the paper its headline result, and the
paper and the record together are what a CV can point to. So the plan below
is one sequence, and every step says which goal it serves.

## Where things stand (2026-10-13)

| | status | evidence |
|---|---|---|
| Chapter 1 model | **verified**: the community TAS (19 rooms, 2,275 frames of control) plays exactly; 16 recordings from Celeste 1.4 match on every frame, subpixels included (the longest 880 frames, 8 rooms, to a death); the map's tiles outside the rooms are in the model | `tests/chain_tas.py`, `tests/recordings.py data/recordings` |
| Model self-consistency | **verified**: 2.95 M fuzzed frames bit-identical between the literal and the solver build; the SAT harnesses' input rules (2.0 M checks) and state comparison (6.8 M) fuzzed too | `tests/diff.sh` |
| SAT finds frames humans left | **one confirmed in the game** (`lvl_3`, 107 → 106), but it costs the next room its setup; five more room endings faster in the model, all costing the next room | [docs/results.md](docs/results.md) |
| Local optimality (Tier B) | **W = 12 and 16 over all of Chapter 1** (3,826 windows proven, 6 timeouts), W = 18 over room 1; all 18 room transitions proven at two window sizes | `results/leonardo/`, `hpc/summary.py` |
| Faster than the community TAS | **nothing yet.** The 15 "faster" Leonardo windows are faster room *endings* in a different state; after each, the next room's TAS inputs fail. The `lvl_6a` lead (118 frames instead of 161, over the top of the room) **fails in the game**: there is wall above the room, now in the model too | [docs/results.md](docs/results.md#the-leonardo-campaign-october-2026) |
| Chapter 2 model | dream blocks, chasers, switch gates, barriers modelled and fuzzed. **Three recordings match on every frame** (the longest 851 frames over 5 rooms, to a death in `2a_lvl_7`, the switch gate's position included), after four fixes found with them: the dream-dash entry and exit frames, the 1.4 dream-block exit push, and the touch switch's 16 × 16 box | [docs/verification.md](docs/verification.md#chapter-2-one-recording-so-far) |
| Chapter 2 routes | made with the dream-block bug, so **all to be re-solved**: `results/routes/2a_chase.tas` dies in `2a_lvl_4` in the fixed model. Before the fix the project's own search was ~9 % behind the community TAS over the chase (rooms 4-12: 2,429 vs 2,221 frames) | `tools/chain_chapter2.py` |
| Own search vs humans | beam + polish from the spawns: 100 / 114 / 127 frames on Chapter 1 rooms 1-3, where the TAS (entering from the room before) takes 92 / 118 / 107 (room 2 is faster only by giving up the TAS's speed into room 3) | `tools/run_tests.sh --vanilla` |

The record to beat for Chapter 1 is the community TAS's **0:49.079** (2,887
frames on the in-game timer; `ChapterTime` in VampireFlower/CelesteTAS
`1A.tas`; the file is the same at the repository's latest commit as of
2026-10-12). Every frame of control saved without
changing how any room is entered or left takes one frame (17 ms) off it.

---

## Step 1 -- the Leonardo results (done 2026-10-13)

`results/leonardo/`, read with `hpc/summary.py`. What it changed: the
certificate (Tier B) is real and covers all of Chapter 1, and the "15 frames"
are not a saving (step 2).

## Step 2 -- the Chapter 1 record attempt (weeks; goal 1, the paper's headline)

The window proofs say the community TAS has no local slack: everything the
SAT solver can still find is a different *ending* of a room, which then has
to be paid back in the next room. So the frames are in the seams. Two
things to do, in order:

1. **The tiles outside the rooms (done 2026-10-13).** The `lvl_6a` lead
   (118 frames, TAS 161) ran along above the room's top edge, where the
   model had nothing. In the game there is wall there: `LevelLoader` copies
   a room's solid top-row tiles 3 tiles up, as high as she can go. The
   model now has the map's tiles around every room, and the recording of
   the attempt matches it to the frame she dies. The lead is void. Re-run
   the Chapter 1 beam sweeps with the new rooms: other "faster" routes that
   leave a room's area are void too, and the search may find different
   ones.
2. **The faster endings.** `lvl_6a` −5, `lvl_12` −4, `lvl_9b` −3, `lvl_3b`
   −2, each in a different exit state. Each is worth something only if the
   next room can be done from the new entry within (TAS frames + saving − 1).
   That is one beam search per candidate, e.g. `lvl_12a` from the
   145-frame `lvl_12` ending in < 143 frames. `hpc/candidate_checks.sbatch`
   is the template.

When a candidate checks out in the model, play it in the game. Then:

- If the time is lower, open a pull request against VampireFlower/CelesteTAS
  with the new `1A.tas`. Credit the method and link the repository. In
  Celeste the TAS record is the community file, and TASers verify it by
  playing it. Ask in the Celeste TAS community before you call it a record
  publicly.
- If a room desyncs in the game, that is a model bug: record it, fix it, add
  the recording.

## Step 3 -- make Chapter 2 trustworthy (2-4 weeks; the paper's second chapter)

Chapter 2 has met the game once, and the meeting found a bug. Settle the
model before spending more compute on it.

1. **The chase recordings (done 2026-10-13).** Three recordings, two of
   them the same run (the second with the switch gate's position), now match
   the model on every frame: `2a_lvl_3` to `lvl_6` and 151 frames of
   `lvl_7`, to a death on frame 152 in both, 851 frames; the gate is where
   the game has it on all 334 frames of `lvl_6`. Getting there took four
   fixes ([docs/verification.md](docs/verification.md#chapter-2-one-recording-so-far)):
   the dream-dash entry frame, the dream-dash exit frame, the 1.4 push back
   towards the block on leaving it without a jump, and the touch switch's
   box (16 × 16, which commit 1d3e148 had right; the 30 × 30 box of the
   ILSpy line is the feather collider). Next: **re-solve the chase**
   (`tools/chain_chapter2.py --polish`; every Chapter 2 route was made with
   at least one of these bugs), write a new `results/celestetas/2a_chase.tas`
   and record it.
2. **The community 2A TAS through the model.** This is the cheapest strong
   check there is, the same one that made Chapter 1 believable. A first try
   (2026-10-13, before the dream-block fix) failed in `2a_lvl_4`. `2a_lvl_3`
   has a dream block, so try again with the fix first. Its `lvl_3` starting
   state was reconstructed by scanning start positions, because the TAS
   plays part of `lvl_3` before the intro cutscene. Generalise
   `tests/chain_tas.py` to a chapter argument: the rooms and goals come from
   `tools/import_chapter2.py`, the chase starts in `lvl_3` after the cutscene
   skip (the TAS's `1,S` lines), and the chaser history runs on across rooms.
   Every room's inputs must leave it on their last frame. Where they don't,
   the model is wrong.
3. **More recordings** for what the chase recording does not reach: the
   chaser's wake-up delay after a respawn, a dream-block exit into a climb
   and into a solid, and the switch gates' timing.
4. Only then: windows over the community 2A TAS (`hpc/make_tasks.py`
   generalised to a chapter), the same way as Chapter 1. Don't race the
   community TAS with the beam search. It is ~9 % behind over the chase,
   and the dense chaser geometry makes the human routes harder to beat, not
   easier.

## Step 4 -- the paper (start writing during step 2; ~2 months to a submission)

**The contribution**, in one sentence: *a frame-exact executable model of
Celeste's player physics, validated against the real game, used with a SAT
solver to (a) certify that no local change of up to W frames improves a
human world-record TAS and (b) find the places where one does, verified in
the game.*

**What it may claim** (see [docs/methods.md](docs/methods.md#what-proven-means)):
Tier A (fidelity) for Chapter 1, and Tier B (local optimality, W = 12/16,
all room transitions) for the whole chapter. That is already a result: the
human world record has no local slack the solver can find. Add N frames
saved in the game once step 2 delivers them. **What it must not claim**:
optimality of a room or a run (Tier C/D), or any number that has not been
reproduced from committed data.

**Evaluation it needs:**
- fidelity: the community TAS, the recordings, the fuzzer counts, and the
  model bugs found by recordings (falling-unduck, the upward stop point, the
  climb trigger; in 2026-10 the dream-dash timing, the 1.4 dream-block exit
  push and the tiles outside the rooms) as evidence that the checks have
  teeth;
- the certificate: windows per room and W, proven / timeout / faster, core-
  hours;
- scaling: proof time against free frames (the ~1.5x per frame), formula
  size, the solver comparison (MiniSat vs Kissat/CaDiCaL/Bitwuzla/Z3, in
  [docs/methods.md](docs/methods.md#scaling)), redone on the final model;
- the frames saved, each with its in-game recording;
- an honest comparison of the project's own search with the human TAS.

**Related work to cover:** TAS tooling and the Celeste TAS community
(CelesteTAS, libTAS, TASVideos), complexity results for platformers
(Mario and friends are NP-hard or PSPACE-complete), game-playing agents on
platformers (the Mario AI benchmark, RL on Celeste such as celeste-rl),
bounded model checking of software (CBMC), and SAT/SMT applied to games and
puzzles.

**Venues** (check the current calls for papers): the SAT conference
(applications), TACAS or CAV (tool papers), IEEE Conference on Games, AIIDE,
Foundations of Digital Games. Put a preprint on arXiv first, which also
dates the result. A workshop paper on Chapter 1 alone is a reasonable first
target.

**An artifact.** A Dockerfile (Ubuntu + gcc + cbmc), `tools/run_tests.sh`,
and a script that rebuilds every number in the paper from `results/`. The
game files can't be included. Say so and document `game/README.md`.

## Step 5 -- before you point people at the repository (days; goal 3)

- **Choose a licence** for your own code (MIT, matching the ported
  `Player.cs`, is the natural one). The repository has none, which legally
  means nobody may reuse it. `THIRD_PARTY_NOTICES.md` stays as it is.
- **Game content in the git history.** This cleanup removed
  `1-ForsakenCity.bin` (the game's map file) and the community TAS copies
  from the tree, but they are still in the history of a public repository.
  So are the ILSpy outputs committed on 2026-10-13 (`LevelLoader.cs`,
  `Switch.cs`, `SwitchGate.cs`, decompiled game code, the most clearly not
  ours) and `data/recordings/log.txt` (an Everest log with local paths).
  Rewrite the history (`git filter-repo --invert-paths --path
  1-ForsakenCity.bin --path LevelLoader.cs --path Switch.cs --path
  SwitchGate.cs --path data/recordings/log.txt`, likewise
  `recordings/1A*.tas` and `results/celestetas/celeste-sat-community-1a.tas`)
  and force-push. It is destructive and changes every commit hash, so decide
  deliberately and do it before anyone forks. The Chapter 2 room exports
  (`rooms/vanilla/2a_*.txt`) are game-derived too. Consider keeping only
  `tools/import_chapter2.py` and its `EXIT_FIXES`.
- **Show it.** A 30-second video of the record attempt playing in the game,
  next to the model's trace (`tools/render.py` makes the replay page), at the
  top of the README. A short write-up or blog post that tells the story, with
  the honest numbers.
- **On the CV**, the strongest true lines: *built a frame-exact model of
  Celeste's physics in C, validated against the real game to the subpixel;
  used CBMC/SAT to certify local optimality of the human world-record TAS
  over ~4,300 windows on EuroHPC Leonardo (~2,300 core-hours); found N
  frames the record missed, verified in the game*. N and "verified" only
  once step 2 is done.

## Step 6 -- a stronger search (months; more records)

The beam search is the bottleneck for anything beyond the human route. In
order of expected payoff:

- **Large-neighbourhood search seeded from the human TAS.** This is what
  the window proofs already are, done as search instead of proof. Re-plan a
  window of 20-60 frames with the beam search, require the end state to
  match (`same_future`) or to be better, splice, repeat.
- **Macro-action search.** Search over moves (dash in a direction on a frame,
  super, hyper, wavedash, wallbounce, climb jump, neutral) instead of frames.
  Branching drops from ~500 per frame to ~20 per move, and every node is a
  state a human route could contain. Keep the per-frame beam for the polish.
- **Pareto chaining across rooms.** The TAS gives up frames in one room to
  set up the next (`lvl_2`, `lvl_8`, `lvl_12`). Keep a set of
  non-dominated exit states per room instead of the single best one, and
  run a DP over the chapter. `model/state_eq.h` and `tools/cross.py` are the
  pieces. Start with dominance only between identical states.
- **Wider seams.** `hpc/crossings.sbatch` with `BEFORE=10, AFTER=8` on the
  six rooms whose endings can be faster (`lvl_2`, `lvl_3`, `lvl_4`, `lvl_3b`,
  `lvl_8`, `lvl_12`). That is where a human TAS is weakest.
- Search hygiene: hash the chaser history in chase rooms
  ([docs/developing.md](docs/developing.md#known-warts)); sweep the rollout
  length per room (`hpc/beam_sweep.sbatch`) instead of trusting 8.

## Step 7 -- a higher proof ceiling (research; the paper's future work)

Each frame added to W multiplies proof cost by ~1.5, so encoding work pays
compound interest:

- **Cheaper collisions.** About half of the ~250,000 variables per frame are
  hitbox checks. Precompute each frame's collision features once from the
  8x8 window. Halving the formula is worth ~1.7 free frames on every query.
- **Cube and conquer.** Split on the discrete skeleton (the frame each dash
  starts, which wall a jump uses) and solve the cubes in parallel. This
  turns core-hours into W, which is what a cluster allocation buys.
- **Lower bounds by abstraction** (the only road to Tier C). Prove "cannot
  leave before frame L" on a coarser, sound model (interval speeds,
  nondeterministic rounding), refine where it finds a spurious route.
  Prototype on `ledge`, which now has an open question of exactly the right
  size: the full model has a 17-frame route (`results/routes/ledge_17.tas`).
  Is 16 possible?
- **A proof ledger.** One row per result: room, entry-state hash, window, W,
  model commit, solver version, verdict, seconds. Without it a model change
  silently invalidates months of compute.

## Step 8 -- more chapters (months each)

Run the entity census over every map before choosing
(`python3 tools/entity_census.py game/ --json census.json`). The expected
backlog, easiest first: cassette blocks, wall springs, two-dash refills,
moving blocks (the zip mover template); feathers and wind (new movement
states and scripted forces); holdables, seekers and the Badeline boss (these
change the problem, not only the model). The discipline that made Chapter 1
believable applies to every entity ([docs/developing.md](docs/developing.md#adding-a-mechanic-an-entity-a-state)):
a generator in the fuzzer, a green fuzz run, an in-game recording.

---

## Claims to avoid

Some descriptions of the project that have been in circulation are wrong.
They would not survive a reviewer or a TASer:

- *"An autonomous Chapter 1 speedrun in 0:49.079."* That was the community
  TAS itself (see [docs/history.md](docs/history.md#2026-10-12-cleanup-and-an-audit-of-the-claims)).
  The project's own search is several frames per room behind it.
- *"The human WR is 0:37.9 (2,275 frames)."* 2,275 is the TAS's frames of
  control; its chapter time is 0:49.079. The two numbers can't be compared.
- *"15 frames shaved off Chapter 1."* The 15 frames are faster room endings
  in a different state, and the next room's TAS inputs fail after every one
  of them. They are leads, not savings.
- *"4,338 windows mathematically proven optimal."* Each proves that one
  stretch of the route can't be shortened to the same state, within the
  model. That is local optimality (Tier B), not optimality.
- *"Chapter 2 is the best candidate to beat the human WR."* The Chapter 2
  model has not been checked against the game, and the project's chase
  routes are ~9 % slower than the community's.

## Risks

- **Fidelity compounds.** Only `Player.cs` is published. Every other entity
  is the game's code as read or remembered, and a wrong rule invalidates
  every route and proof built on it. The in-game recording at each step is
  the control. Plan for one recording session per chapter.
- **The community moves.** The record is a living file. Check the latest
  `1A.tas` before submitting.
- **Compute without a ledger rots.** See step 7.
- **Tier D will be asked for anyway.** Have the tier table ready
  ([docs/methods.md](docs/methods.md#what-proven-means)).
