# ROADMAP — from one chapter to "calculating Celeste"

Written 2026-10-04. Goal as stated: model the whole game exactly and beat the
community TAS. This document says what that can and cannot mean, then gives
the order to build it in.

Read `brain.md` first for the current state. This is the long view.

---

## 1. What "calculate all of Celeste" can actually mean

The project has one hard physical limit, and the whole plan is shaped by it.

**SAT proof cost grows ~1.5x per free frame.** Measured, from the README:

| free frames | room | time |
|---|---|---|
| 5 | `ledge` | 33 s |
| 9 | `ledge` | 204 s |
| 11 | Chapter 1 room 1 | 129 s |
| 12 | `hop` | 435 s |

Extrapolating the same 1.5x: ~17 frames is an hour, ~24 frames is a day,
~35 frames is a decade. Proving a single 100-frame room optimal from nothing
is about `1.5^89` times a two-minute query. That is not an engineering gap, it
is a wall. No solver choice fixes it — the README already found Kissat,
CaDiCaL, Bitwuzla and Z3 all matched or lost to MiniSat, which says the
*encoding* is the cost, not the search.

Exhaustive search is no better: distinct states grow ~4x per frame (1.8 M by
frame 8), because input timing leaves different subpixels.

So "calculate Celeste" has to be split into claims of different strength:

| tier | claim | status |
|---|---|---|
| **A. Fidelity** | the model reproduces the game frame-for-frame, subpixels included, on every room of the run | done for Chapter 1; the method is proven (CelesteTAS recordings) |
| **B. Local optimality** | no stretch of ≤ W frames of this route can be done in W−1 frames and reach the same state | done for one 92-frame room at W=8; **whole-game is a compute problem, not a research problem** |
| **C. Room optimality** | no route through this room, from this entry, is faster | done only for tiny demo rooms; needs lower-bound research (§6) |
| **D. Run optimality** | no route through the game is faster | **not reachable.** Say so plainly, forever. |

**"Cracking the WR TAS" = Tier A + Tier B + a search strong enough to find
improvements.** That is a real, defensible, publishable result: *a frame-exact
model of the game, a route that beats the human TAS, and a machine-checked
certificate that no small local change improves it further.* Tier D is not on
the table and claiming it would be dishonest.

Note also that the WR TAS is a **moving target** maintained by a community
(`VampireFlower/CelesteTAS`). "Cracking it" in practice means contributing
verified frame savings back, repeatedly — not a one-shot conquest.

---

## 2. The one calculation that sets the budget

Tier B over the whole game is the headline deliverable, so price it now.

A window proof needs one CBMC query per start frame. At W=8 that is ~1–3 min
per query (measured). Frames of *control* (not wall-clock; transitions and
cutscenes are free):

- Chapter 1 A-side: **2,275 frames** (measured)
- Chapter 2 chase: ~2,100–2,500 frames (measured)
- so ~2,000–2,500 per chapter, and an any%-shaped run of 8 chapters is
  **~16,000–20,000 frames of control**
- a full clear (B/C sides, Core, Farewell) is perhaps 5x that

| certificate | per query | 20,000 frames | feasible? |
|---|---|---|---|
| W = 8 | ~2 min | **~670 core-hours** | yes — a weekend on 16 cores |
| W = 12 | ~8 min | ~2,700 core-hours | yes — days on a cluster, ~$300 spot |
| W = 16 | ~65 min | ~21,700 core-hours | borderline, ~$2–3k spot |
| W = 20 | ~8 h | ~160,000 core-hours | no |

**The practical ceiling is W ≈ 12–16 for a whole run.** That is the honest
scope of the end state: *"no local change of up to 12–16 frames improves this
route, anywhere in the game."* Everything in §6 is about pushing that number,
and every frame gained there is worth 1.5x the compute.

This budget is also why §3–§5 come first: a window proof is only meaningful if
the model is right (Tier A) and the route is good (search). Proving a bad route
locally optimal is cheap and worthless.

---

## 3. Phase 0 — close out Chapter 2 (days)

Already listed in `brain.md` §8; repeated here for completeness.

1. `sudo pacman -S cbmc`. Half the project is unreachable without it.
2. **Record the chase in the real game.** `results/celestetas/2a_chase.tas` is
   ready; `tests/recordings.py <Celeste folder>` checks it room by room. This
   is the Tier A leg for Chapter 2 and settles the dream block's timing, the
   chaser's 1.55 s delay and its 6x6 hitbox, all currently inferred.
3. **Invisible barriers** (static solids, ~an hour) — `2a_lvl_2`, `2a_lvl_9`,
   `2a_lvl_10` currently let a route walk through walls that exist.
4. Re-run `tools/chain_chapter2.py` and replace `results/2a_chase.tas`, which
   predates the merged chaser and the two model fixes.
5. Fix the `--beam-rollout` default mismatch (8 vs 10) and sweep it.
6. Re-run the SAT descent on `ledge`: there is a 17-frame route, the saved one
   is 18, and the demo-room table is stale.

---

## 4. Phase 1 — measure, then close, the entity backlog (months)

This is the long pole for "all of Celeste", and it must be **measured, not
guessed**.

### 4.1 The census (first task, one afternoon)

`tools/import_map.py` already prints every entity per room and flags the
unmodelled ones. Run it over all ten map files and aggregate. For Chapter 1,
done today:

```
38 rooms. Gameplay entities: jumpThru, spikes{Up,Down,Left,Right}, zipMover,
spring, crumbleBlock, refill, fallingBlock, fakeWall, dashBlock, cassetteBlock.
Decoration: wire, strawberry, lightbeam, bonfire, npc, memorial, flutterbird,
birdForsakenCityGem, checkpoint, coverupWall, player (spawn markers).
```

**Chapter 1 A-side is fully modelled** — the only unmodelled gameplay entity
in the whole chapter is `cassetteBlock`, in `lvl_11z`, a cassette side-room off
the main route. That is a genuinely strong position to build from.

Write `tools/entity_census.py`: for each map, for each room, list unmodelled
entities, and weight them by whether the room is on the TAS's route (parse the
community TAS's room order). Output a ranked worklist. Everything below is a
guess until that script exists — write it first.

### 4.2 Expected shape of the backlog

From the README's own "not modelled yet" list plus what the chapters contain,
in rough order of difficulty. **Treat this as a hypothesis for the census to
confirm or refute.**

**Easy — static or table-driven, like the solids already done:**
- `cassetteBlock` (Ch1 side rooms, Ch2+): solid, toggles on a global beat.
- wall springs, two-dash refills, `MAX_DASHES` > 1.
- bumpers, `moveBlock` / `swapBlock` / `bounceBlock` (Kevin) — all moving
  solids with a coroutine, the same shape as `ZipMover`, which is already
  factored (`CUR_MS_BOX`, `ZIP_KIND`). The switch-gate work on the merged
  branch is the template: a new kind, a new table from `make_room.py`.
- `coreModeToggle` and the Ch8 hot/cold mode bit: one global flag plus
  fire/ice block variants.

**Medium — new movement states, like the dream dash:**
- **Feathers.** A whole alternate movement state (`StStarFly`) with its own
  physics, timer and exit. Precedent: `ST_DREAM_DASH` cost one state, a timer
  and two flags. Budget similar.
- **Wind** (Ch4). A per-room, time-varying global force. Needs a table per
  room like the zip mover paths; the hard part is that it is *scripted per
  room* and the data lives in the map file.
- **Water, climb blockers, no-grab regions.** Mostly collision-layer work.

**Hard — these change the problem, not just the model:**
- **Holdables** (Theo crystal Ch5, jellyfish Ch9). A second actor with its own
  physics, carried, thrown, standing on. Roughly doubles the state and adds a
  continuous throw parameter. Expect the SAT formula to grow a lot.
- **Seekers** (Ch5). Adversarial, with their own pathfinding. The Badeline
  chaser was tractable because it only replays *her* recorded positions; a
  seeker runs a real chase AI. This is the single most expensive entity.
- **Badeline boss** (Ch6). Scripted phases with their own timing; may not fit
  the room-with-an-exit paradigm at all.
- **Cutscenes and triggers.** Already hit once: `SPAWN_FACING` exists because
  `CS02_BadelineIntro` leaves her facing left. Every chapter has more.

### 4.3 The discipline, non-negotiable

`brain.md` §6 states it; it is the reason the project is credible. For each new
mechanic:

1. a `; directive` in the room format and `make_room.py` export,
2. a **`tests/random_room.py` generator**,
3. a `tests/diff.sh` run, green, with a coverage counter proving it fired,
4. `same_future` + `scramble()` entries for any new live state,
5. `transition.h` + `chapter.py` entries for anything the transition clears,
6. an in-game recording that matches frame-for-frame.

Steps 2–4 are what Chapter 2 skipped, and the fuzzer found two real bugs the
moment they were done. **Do not let a mechanic reach a route before step 3.**

Most of these entities are decompiled-from-memory, not from published source —
only `Player.cs` is public. Fidelity risk compounds with every chapter, and the
recording in step 6 is the only control. Budget a recording session per
chapter, not per project.

---

## 5. Phase 2 — make the search strong enough to beat humans (the real bottleneck)

Today the beam search finds 99 frames where the TAS takes 92 on Chapter 1 room
1, and 133 vs 107 on room 3. The README is honest about why: *"it never dashes
or wall-boosts on its own, and those are what the TAS routes are built from."*

Until this is fixed, Tier B certificates are certificates about mediocre
routes. Three ideas, in order of expected payoff.

### 5.1 Macro-action search (highest leverage)

Per-frame input space is ~3·3·3·3·2·3 ≈ 500 combinations per frame. Human
TASers do not think that way — they think in **moves**: dash in a direction on
a frame, super, hyper, wavedash, wallbounce, climb jump, demodash, neutral.
Maybe 20 macros, each spanning 3–15 frames.

Search over macro sequences, with the exact model as the executor. Branching
collapses from ~500/frame to ~20/move, and every node is a state a human route
could contain. This is the single change most likely to close the 99-vs-92 gap.

Implementation: a macro is a function `State -> [Input]` plus a validity
predicate. Reuse `search/beam.c`'s beam and ranking; replace the per-frame
expansion with macro expansion. Keep the per-frame beam as a fallback and for
the final polish, since the optimum is not always macro-aligned.

### 5.2 Large-neighbourhood search seeded from the human TAS

`--polish` already restarts the beam from frame K of the best route, on a fixed
schedule (K = U−15, U−25, …). Generalise it:

- pick a random window of 20–60 frames anywhere in the route,
- re-plan it with the macro search, requiring the end state to `same_future`
  the original (or to be Pareto-better),
- splice and repeat; accept improvements, keep a tabu list.

This is how good TAS tooling works in practice, and it uses the human TAS as
the seed rather than competing with it from scratch.

### 5.3 Pareto frontiers per room, and DP across rooms

This is the open problem the README names: room 2 has three endings (114, 117,
118 frames) that leave different states, and *"rooms have to be optimised
together"*. `tools/chapter.py` currently carries **one** exit state forward.

Fix: per room, keep the **Pareto-non-dominated set** of (exit frame, exit
state) pairs rather than the best one. Then run a DP over the room graph: the
cost to reach room *n* in state *s* is the min over predecessors. Width-bounded
(keep the best K states per room, deduplicated by `same_future`) this is
entirely implementable and directly targets the stated gap.

Two pieces already exist: `model/state_eq.h` gives state equality, and
`tools/cross.py` gives the transition. What is missing is a dominance relation
— "state A is at least as good as B" — which is genuinely hard in a game with
speed retention and buffered presses. Start with the safe version: dominance
only on identical states at earlier frames, everything else kept as a distinct
frontier point.

### 5.4 Optional, higher cost

- **Bidirectional search**, backward from the room exit. The backward model is
  not trivial (movement is not invertible through collisions) but a relaxed
  backward distance would sharpen the beam's ranking a lot.
- **A learned value function** as the beam heuristic. Likely effective, a large
  detour, and it makes nothing *provable* — it only improves upper bounds.

---

## 6. Phase 3 — push the proof ceiling (research)

Every frame added to W multiplies compute by 1.5, so encoding work pays
compound interest. In order of expected payoff:

### 6.1 Cheaper collisions

The README estimates ~250,000 variables per frame, *"about half collision
checks"*. A frame currently does ~50 separate hitbox queries. Precompute each
frame's local collision features once — the solver build already loads an 8x8
tile window (`WCOL`), so the structure is there. **Halving the formula is worth
~1.7 free frames**, for free, on every query ever run after it.

### 6.2 Cube and conquer

Split on the discrete skeleton — which frame each dash starts on, whether it is
cancelled, which wall a jump uses — and solve the cubes in parallel. This
converts wall-clock into core-count, which §2 says we can buy. Expect this to
be the cheapest way to move W from 12 to 16.

### 6.3 Lower bounds by abstraction-refinement (the only route to Tier C)

Prove *"cannot exit before frame L"* on a coarser, sound over-approximation —
fixed-point or interval speeds, nondeterministic rounding — where SAT is cheap,
and refine only where it reports a spurious route. If L meets the best known
route, the room is proven outright, regardless of length.

This is the single highest-value research item in the project. It is the
difference between "no local improvement" (Tier B) and "this room is optimal"
(Tier C). It is also the most likely to fail — the abstraction has to be loose
enough to be fast and tight enough not to admit spurious routes through every
wall, and Celeste's subpixel mechanics are exactly what abstraction destroys.
Prototype it on `ledge` and `hop` before committing.

### 6.4 Waypoints

Split a long room at states every route must pass (a gap, the top of a block)
and prove each part. Sound only if the waypoint is genuinely unavoidable, which
itself needs proof — but for rooms with a single-tile chokepoint that is easy
to establish from the tile grid.

---

## 7. Phase 4 — infrastructure the scale demands

None of this is interesting, and all of it is required before spending
thousands of core-hours.

- **A proof ledger.** `brain.md` §6 notes model changes invalidate saved
  proofs, and nothing currently tracks that. Record every result as
  `(room, entry-state hash, window start, W, model hash, solver+version,
  verdict, seconds)`. Without the model hash, a stale proof is worse than no
  proof.
- **A cluster harness.** `tools/windows.py` and `tools/cross.py` already
  parallelise locally with `--jobs`; generalise to a job queue with
  checkpointing, since W=12 runs take days and will be interrupted.
- **Regression on the model, not just the builds.** When a mechanic changes,
  re-run every affected recording automatically and invalidate the ledger rows
  whose model hash no longer matches.
- **`tools/entity_census.py`** (§4.1) in CI, so a newly supported entity
  immediately shows which rooms it unlocks.

---

## 8. Phase 5 — the actual record attempt

### 8.1 Pick the right target first

Not any%. Start with **individual-level (IL) records for Chapter 1 A-side**:

- the model is fully validated there (Tier A done, §4.1),
- the room set is small and every entity is supported,
- SAT has *already* found two frame savings on the human route (`lvl_3` 107→106
  confirmed in-game, `lvl_2` 118→117 in the model),
- an IL is a self-contained, submittable, verifiable claim.

Then: Chapter 1 full-chapter, then Chapter 2, then any%.

### 8.2 The loop, per chapter

1. Model every entity on the route (§4), recordings green.
2. Seed from the community TAS; run macro + LNS search (§5) for improvements.
3. Chain rooms with the Pareto DP (§5.3) — this is where the frames actually
   are, because the human TAS deliberately gives up frames in one room to set
   up the next (`lvl_8`, `lvl_12`, `lvl_2` all do), and no human can search
   that trade-off exhaustively.
4. **Record every claimed improvement in-game before believing it.** The
   106-frame `lvl_3` is the model for this: found by SAT, replayed in Celeste
   1.4, every frame matching. The same section also shows why it matters — the
   106-frame ending *breaks* the next room's inputs, so a frame saved locally
   was not a frame saved overall.
5. Run the Tier B certificate at the largest W the budget allows (§2).
6. Publish the route, the recording, and the certificate together.

### 8.3 Where the frames most likely are

Based on what the project has already seen:

- **Room boundaries**, by a wide margin. The human TAS optimises room-locally
  and hand-tunes the seams; the Pareto DP is the first tool that can search
  seams exhaustively. The README's own worked example (room 2's 114-frame
  ending needing a ≤110-frame room 3) is exactly this, left unresolved for want
  of search strength.
- **Rules humans under-exploit** because they are invisible: the 5 px
  wallbounce reach, the 5 px ceiling correction while dash-attacking, two keys
  per button. The project's 99-frame room 1 already relies on a 5 px ceiling
  correction that was *inferred and then confirmed*.
- **Not** raw per-room optimisation. The beam is behind the humans there and
  will be for a while.

---

## 9. Milestones

Effort is wall-clock for one person working steadily; compute is separate.

| # | milestone | effort | gate |
|---|---|---|---|
| M0 | Phase 0 done: Chapter 2 recorded in-game, barriers modelled, chase re-run | days | cbmc installed |
| M1 | `tools/entity_census.py`; ranked backlog for all 10 maps | 1 day | you have the map files |
| M2 | Macro-action search beats the human TAS on Chapter 1 room 1 (≤ 92 frames) | 2–6 weeks | — |
| M3 | Pareto DP chains a whole chapter and beats the human TAS end-to-end on Chapter 1 | 2–4 weeks | M2 |
| M4 | Tier B certificate, W=8, for all of Chapter 1 | days | ~120 core-hours |
| M5 | Chapter 1 A-side IL submitted, in-game verified, with certificate | 1 week | M3, M4 |
| M6 | Cheaper collisions (§6.1): formula halved, W+1.7 for free | 2–4 weeks | — |
| M7 | Chapters 3–5 modelled, recordings green | 2–4 months | M1 |
| M8 | Cube-and-conquer: W=16 practical | 1–2 months | M6 |
| M9 | Chapters 6–9 modelled (seekers, holdables, boss) | 4–8 months | M7 |
| M10 | Whole any% route, beaten end-to-end, W=12 certificate | — | M9, ~2,700 core-hours |
| M11 | Abstraction-refinement lower bounds: Tier C on real rooms | open-ended | M6; may fail |

M0–M5 is the credible first result and is maybe three months. M10 is the
"cracked the TAS" headline and is realistically **a year or two**, dominated by
M9 — modelling seekers, holdables and the Badeline boss faithfully enough to
survive an in-game recording.

---

## 10. Risks, stated plainly

- **Fidelity risk compounds.** Only `Player.cs` is published. Every entity
  after Chapter 1 is decompiled-from-memory, and the model has already needed
  rules found only by recording (falling-unduck waiting for coyote time; the
  climb jump that starts a zip mover). A wrong rule invalidates every route and
  every proof downstream of it. Mitigation: §4.3 step 6, every chapter.
- **Seekers and holdables may not be tractable at all** inside a SAT harness.
  If a holdable doubles the state, W drops by several frames for those rooms.
  Plan to fall back to Tier A + search (no certificate) in those rooms rather
  than stalling.
- **The proof ledger problem is real and unglamorous.** Without §7, a year of
  compute silently rots the first time a mechanic changes.
- **Determinism must be confirmed per entity.** The TAS community relies on
  Celeste being deterministic, but confirm it for each new entity rather than
  assuming — anything seeded from the save file or from `Scene.TimeActive`
  rounding (the chaser already needed a 3-frame conservative window for exactly
  this reason) is a trap.
- **Tier D is impossible and will be asked for anyway.** Have §1's table ready.
  The honest headline is *"frame-exact model, route beats the human TAS, no
  local improvement up to W frames exists"* — which is a strong result, and
  much stronger than most TAS work has ever had.
