# Methods

How routes are found and how the SAT solver is asked about them: one room
(`tools/solve.py`), windows inside a known route (`tools/windows.py`), rooms
in sequence (`tools/chapter.py`) and queries across a room transition
(`tools/cross.py`); then what the proofs cost and what "proven" means.


## How the pipeline works

1. **Beam search** (`search/beam.c`) keeps the best 100,000 distinct states
   per frame (at most 4 per position, state and dash count, so the beam does
   not fill up with sub-pixel variants of one state). States are ranked by
   distance to an exit along a pixel-level shortest path through the room,
   after a short rollout that steers along that path (so states in the middle
   of a dash freeze are valued by where the dash takes them). It returns a
   real route: an upper bound U.
2. **Polish** (`--polish`) restarts the beam from the state after the first K
   frames of the best route, for K = U−15, U−25, …, and keeps any shorter route.
3. **SAT descent** asks CBMC: *is there any input sequence that leaves the room
   by frame U−1?* A counterexample is a faster route; it is replayed in the
   simulator (the two must agree) and the question is asked again. When CBMC
   answers "VERIFICATION SUCCESSFUL", no route of that length exists, so the
   current best is optimal within the model.
4. `--from-frame K` holds the first K frames fixed and makes everything after
   them free. The proof then says: *given this opening, nothing is faster.*
   This is how long rooms become tractable (see "Scaling").
5. **Tidy** replaces inputs after frame K with simpler ones (continue the
   previous input, or nothing) wherever that does not cost a frame. The route
   stays just as fast and becomes readable.


## Windows inside a route

The SAT queries above free the end of a route. `tools/windows.py` frees
every stretch of W frames inside it: for each K it starts CBMC from the
route's exact state after K frames and asks whether any W inputs reach its
state after K + W + 1 frames, i.e. one frame sooner (`harness/window.c`).
A yes makes the rest of the route work unchanged a frame earlier: it is
spliced in and replayed. A no proves that this stretch cannot be shortened
to the same state.

The state is compared on the fields that can still change the rest of the
route. `sim/live.c` finds the others by replaying the rest of the route with
each field changed: `onGround` is recomputed every frame, a dash cooldown
that runs out before the next dash does not matter, and so on. On the
community TAS's `lvl_1`, 9–14 of the 17 candidate fields are dead at the
frames tried. That is a test rather than a proof, so a route found with fields
left out is replayed, and the window is asked again comparing everything if
the replay is not faster. A "no" is a statement about every state that agrees
on the compared fields, which includes the route's own state. The dominance
rules on buffered presses are off in a window's last 5 frames, where a press
can leave a buffer the target state has.

On the demo room `ledge`, with one idle frame added at the start, the first
window finds the wasted frame and the next one proves no saving (about 5 min
each). Windows of 8 frames on the community TAS take about a minute each.

On the community TAS's `lvl_1` (92 frames), all 83 windows of 8 frames
(frames 1–9 up to 83–91) are "no": no stretch of 9 frames of the route can
be done in 8 and end in the same state. About 2 hours on 2 cores. So the
TAS's room 1 cannot be shortened by any local change of up to 8 frames;
a faster room 1 would need a different state somewhere along the way (as
the 106-frame `lvl_3` ending has).


## Rooms in sequence

In a real run each room starts the way the previous one ended. For an upward
exit the game sets her speed to (0, −105) with an automatic full jump,
refills dash and stamina, puts the dash on a 0.2 s cooldown, zeroes the
subpixels and moves her up into the new room until her feet are 9 px above
its bottom edge (5 px in rooms taller than 184 px, see [verification.md](verification.md#things-still-to-check));
her other state (facing, pending wall speed retention, …)
carries over. `tools/chapter.py` searches the rooms one after the other, each
from the state the previous one left her in, for its fastest exit (or
replays given routes with `--routes a.tas,-,-`):

```
python3 tools/chapter.py rooms/vanilla/1a_lvl_1.txt rooms/vanilla/1a_lvl_2.txt rooms/vanilla/1a_lvl_3.txt \
    --polish --out build/chapter1
```

The community TAS shows why the fastest exit is not enough: its routes chain
exactly (the check above, 317 frames of control for rooms 1–3), and its room 2
ending gives up frames there to arrive in room 3 with speed to spare. For
lining up with a known next-room route, `tools/solve.py --exit-x X` makes the
beam search count only exits at that x.


## Across room boundaries

`tools/cross.py` puts two rooms into one SAT query: the end of room A, the
transition, and the start of room B.

```
python3 tools/cross.py rooms/vanilla/1a_lvl_2.txt lvl_2.tas rooms/vanilla/1a_lvl_3.txt lvl_3.tas \
    --start entry_lvl_2.h --keep 106 --target 2
```

A known route crosses both rooms. Its first K frames in A stay fixed and
everything after them is free: the rest of A, the moment she leaves, and B.
The question: can Madeline be in *exactly* the state the known route has
after M frames in B, one frame sooner? Exactly means every field that can
still make a difference (position, subpixels, speeds, timers, buffered
presses; `model/state_eq.h`, checked by the fuzzer), so the rest of the known
route works unchanged: a yes is a faster route through both rooms, and a no
for every frame she could leave A on proves that no route through the window
saves a frame. The two rooms are separate builds of the model linked into one
program (`model_a.c`, `model_b.c`, written by the tool), the transition is C
(`model/transition.h`; on the known route it must agree with
`celeste_sat/transition.py`), and there is one query per frame she could leave A on,
run in parallel (`--jobs`). `--exit-from F` skips the frames before F when a
single-room proof has already ruled them out.

The check in `tools/run_tests.sh --sat`: two stacked demo rooms, `shaft_a`
and `shaft_b`, and a route that waits one frame too long before dashing up
out of `shaft_a` (`tests/fixtures/shaft_a.tas`, 11 + 10 frames). CBMC finds the
20-frame route (one query of about a minute, next to a "no" for leaving on
the same frame).

On the community TAS, each room entered as in the TAS (times are CBMC on one
core, all queries of a window added up):

| free in the first room | target | answer | queries, time |
|---|---|---|---|
| `lvl_1` frames 89–92 | `lvl_2` frame 2 | no | 5, 61 s |
| `lvl_1` frames 81–92 | `lvl_2` frame 2 | no | 13, 19 min |
| `lvl_1` frames 89–92 | `lvl_2` frame 10 | no | 13, 23 min |
| `lvl_2` frames 107–118 | `lvl_3` frame 2 | no, given `lvl_2` cannot be left before frame 117 (single-room proof above) | 3, 7 min |
| `lvl_2` frames 107–118 | `lvl_3` frame 4 | no, given the same | 5, 19 min |
| `lvl_2` frames 111–118 | `lvl_3` frame 8 | no | 15, 35 min |

(Free: the frames listed, the room change, and the next room up to the
target; "`lvl_3` frame 2" means: be in the state the TAS has after 2 frames
in `lvl_3`, one frame sooner.) So within these windows the TAS's room changes
cannot be made faster: no other ending of room 1 or 2 gets into the next
room's TAS state sooner.

What the windows cannot answer is whether a different ending pays for itself
further into the next room. Room 2 has two faster endings in the model:

- 117 frames (SAT, above): leaves at x = 300 instead of 298, moving right at
  111.5 px/s and up at 160 px/s, with no wall speed retention pending.
- 114 frames (the beam search polishing the TAS's route): dash straight up
  the exit shaft from frame 72 (20 frames earlier than the TAS), wallbounce
  off the shaft's left wall on frame 86, wall jump off the right one on
  frame 104. It leaves at x = 278 moving left at 90 px/s.

The TAS's room 3 is built on its entry: two climb jumps against the wall by
the entrance, then the 211 px/s held back by wall speed retention since
room 2 is given back as she clears the wall (242 px/s with the jump's boost,
frame 4), which carries her to x = 97 by frame 18 with the dash still
unused. The other two endings bring no retained speed, so room 3 has to be
solved again from them, and for that the beam search is too weak: from the
three entries it finds 133 (TAS entry; the TAS takes 107), 130 (after 117)
and 127 (after 114) frames. For the 114-frame ending to win, room 3 would
have to take at most 110 frames from an entry at the left wall with no speed
to the right, probably spending the dash on horizontal speed that the TAS
gets from the retention. That is not settled here: it needs a room search as
strong as the TAS, or a room 3 route worked out by hand.

The 114-frame room 2 on its own is worth a check in the game: the model says
it leaves 4 frames before the TAS, with ordinary moves (a dash up, a
wallbounce 1 px from the wall, a wall jump). In the community `1A.tas`,
replace the `#lvl_2` lines from `10,R` to `1,K` (frames 57–118; keep the
`40` after them) by `9,R` / `1,L` / `1,R,J` / `4,L,J` / `1,L,X` / `3` /
`1,U` / `9,L` / `10,L,J` / `1,R,J` / `4,L,J` / `2,L` / `1` / `10,L,J` /
`1,L`. The room should change 4 frames sooner; the `#lvl_3` inputs no longer
fit after it.


## Scaling

Times are CBMC 5.95 + MiniSat on one core. The first rows are from the first
model (one key per button, no climbing).

| question | free frames | answer | time |
|---|---|---|---|
| flat room, exit within N frames | 2 / 4 / 6 / 10 | no | 1.6 s / 8.9 s / 26 s / 190 s |
| `ledge`, exit within N frames | 8 / 10 | no | 88 s / 230 s |
| `ledge`, exit within 18 frames (a solution exists) | 18 | – | stopped after 25 min |
| Chapter 1 room 1, frames 1–94 of a 104-frame route fixed | 9 | no | 13 s |
| Chapter 1 room 1, frames 1–86 of the same route fixed | 17 | no | 17 min |
| Chapter 1 room 1, frames 1–85 of the 102-frame route fixed | 16 | no | 12 min |
| *full model (two keys per button, crouch dash, v1.4 rules):* | | | |
| `ledge`, frames 1–12 / 1–8 fixed | 5 / 9 | no | 33 s / 204 s |
| Chapter 1 room 1, community route, frames 1–80 fixed | 11 | no | 129 s |
| Chapter 1 room 2, community route, frames 1–106 fixed | 11 | yes: 117 frames | 368 s |
| Chapter 1 room 2, same, leave by frame 116? | 10 | no | 193 s |
| Chapter 1 room 3, community route, frames 1–95 fixed | 11 | yes: 106 frames | 173 s |
| Chapter 1 room 3, same, leave by frame 105? | 10 | no | 166 s |

Each extra frame multiplies proof time by roughly 1.5 (less in the middle of a
dash, which leaves few choices). The formula is about 250,000 variables per
frame (about half collision checks, the rest single-precision arithmetic). A
CDCL solver has no arithmetic reasoning: to rule out "exit in 10 frames" on an
open floor, it has to rediscover through bit-level adders that speeds are
bounded. Kissat and CaDiCaL were no faster than MiniSat here, and
Bitwuzla/Z3 on the same formula matched or lost.

Exhaustive search is no better: the number of *distinct* states grows about
4× per frame (1.8 million by frame 8), because different input timings leave
different subpixels.

So the practical recipe is the hybrid above: the beam search for a strong route,
then SAT on windows of up to ~17 free frames, where it either finds an
improvement or proves the window optimal.


## What "proven" means

The SAT solver proves statements about the model, never about the game
directly, and a proof is only as strong as the question it answers. Four
tiers, from what this project has to what it can never have:

| tier | claim | status |
|---|---|---|
| **A. Fidelity** | the model reproduces the game frame for frame, subpixels included, on every room of the route | Chapter 1: done (the community TAS and the recordings, [verification.md](verification.md)); Chapter 2: not recorded yet |
| **B. Local optimality** | no stretch of W+1 frames of this route can be done in W frames and reach the same state (`tools/windows.py`); no ending of a room gets into the next room's state sooner (`tools/cross.py`) | W = 8 on Chapter 1 room 1 here; W = 12/16 over all of Chapter 1 on Leonardo, results not yet committed |
| **C. Room optimality** | no route through this room, from this entry, is faster | only for demo rooms and for the last ~10-17 frames of a room ("given frames 1..K"); needs lower bounds ([ROADMAP.md](../ROADMAP.md)) |
| **D. Run optimality** | no route through the chapter is faster | out of reach: proof cost grows ~1.5x per free frame |

So a claim this project can honestly make looks like: *"a route N frames
faster than the community TAS, played in the real game, and no stretch of up
to W frames of it can be shortened"* -- never *"the optimal route"*.

Two more things a "no" depends on:

- **The fields compared.** Windows compare the states on the fields that can
  still change the rest of the route, found by replaying it with each field
  changed (`sim/live.c`). That is a test, not a proof; a route found with
  fields left out is replayed, and the window is asked again comparing
  everything if the replay is not faster. A "no" is a statement about every
  state that agrees on the compared fields.
- **The model version.** A model change can invalidate any earlier proof.
  Every result should record the commit it was computed at.

What comes next -- lower bounds, cube-and-conquer, cheaper collisions,
macro-action search, Pareto chaining of rooms -- is in [ROADMAP.md](../ROADMAP.md).
