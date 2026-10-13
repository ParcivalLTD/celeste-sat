# Results

Everything here was measured with the model as it is in this repository
unless a section says otherwise, and every route was replayed in the
simulator before it counted. "Proven" always means *within the model*, and
usually *given the frames before the window*: see
[methods.md](methods.md#what-proven-means).

## The record, and how to count it

The community TAS of Chapter 1 (VampireFlower/CelesteTAS, `1A.tas` at the
pinned commit, unchanged at the latest one as of 2026-10-12) records
**ChapterTime 0:49.079 (2887)**: the in-game timer, 2,887 frames counted at
17 ms each, from the level start to the chapter's end, intro and transitions
included. Of those, **2,275 are frames of control** inside the 19 rooms
(the tables below); the rest are the intro (88 frames), the 40-frame room
transitions and the ending. A saving of N frames of control, with every room
still entered and left as before, is N frames off the chapter time.

Two numbers that are easy to mix up: 2,275 / 60 = 37.9 s is *not* a chapter
time, and 0:49.079 *is* the community TAS's -- a route that plays the
community inputs (or this project's chaining of them) in the game shows
exactly that time.


## Chapter 1 in the model

Chapter 1's first three rooms need nothing beyond the model (spikes,
jump-throughs, one spring); `lvl_4` adds a zip mover. For a while the
community TAS's `lvl_4` inputs did not get out of `lvl_4` in the model. A
recording of it in the game (`tools/celestetas.py community lvl_4 lvl_3b`,
with the zip mover's position) showed where: on frame 55 she lands on a
ledge holding Down (ducked), walks off it, and jumps in coyote time on
frame 58; in the game she is still ducked on frame 66 and slips under a wall
that the model, which had stood her up as she started to fall (the published
"falling unducking"), ran into. The game waits for coyote time to end
before standing her up. With that, all 91 frames of `lvl_4` and the 98 of
`lvl_3b` match the recording, and the zip mover is never touched there.

The same recording settled the upward transition's stop point: 9 px above
the bottom edge in `lvl_4` and `lvl_3b` as in `lvl_2`, but 5 px in `lvl_5`,
the first room of Chapter 1 that is taller than a screen plus 4 px. Seven
probe recordings leaving `lvl_1` in different ways (y = 0 to 5, dashing,
ducking or neither) all stop at 9 px in `lvl_2`, so it depends on the room,
not on how she arrives. In `lvl_5` the TAS lands on the zip mover, jumps
off it as it rises (−176 px/s), crouch-dashes into a hyper on it, jumps with
the lift boost capped at −130 (−235 px/s), and climb-jumps up the wall with
the lift still applying; the model plays all 139 frames and leaves on the
last one. Nothing in the zip mover was fitted to this route (the version
before it, and this one without the 0.16 s lift grace, do not get out), so
this checks its timing, carrying, lift boost, caps and grace.

**The whole chapter** (`tests/chain_tas.py`): each room's community inputs
from the state the previous one left her in, rooms exported from the map as
the TAS goes, from the spawn in `lvl_1`:

| room | inputs | model leaves on frame | entities it uses (besides spikes and jump-throughs) |
|---|---|---|---|
| `lvl_1` | 92 | 92 | |
| `lvl_2` | 118 | 118 | |
| `lvl_3` | 107 | 107 | |
| `lvl_4` | 91 | 91 | (zip mover not touched) |
| `lvl_3b` | 98 | 98 | (crumble blocks not touched) |
| `lvl_5` | 139 | 139 | zip mover (rides it up), spring |
| `lvl_6` | 117 | 117 | (refill, dash block not touched) |
| `lvl_6a` | 161 | 161 | refill |
| `lvl_6b` | 110 | 110 | (zip movers not touched) |
| `lvl_6c` | 110 | 110 | spring (dash block not touched) |
| `lvl_7` | 103 | 103 | both falling blocks (they fall during the route) |
| `lvl_8` | 107 | 107 | (falling block, crumble blocks not touched) |
| `lvl_8b` | 99 | 99 | two zip movers, one followed after a climb hop onto it |
| `lvl_9` | 97 | 97 | zip mover with spikes on it, started by a climb jump off it |
| `lvl_9b` | 73 | 73 | (zip mover, crumble block not touched) |
| `lvl_10a` | 204 | 204 | refill |
| `lvl_11` | 161 | 161 | crumble block (crumbles under her), spring |
| `lvl_12` | 147 | 147 | (falling blocks not touched) |
| `lvl_12a` | 141 | 141 | (zip movers not touched) |

**The whole of Chapter 1, 2,275 frames of control in 19 rooms, plays
exactly**: every room's inputs leave it on their last frame, through six
sideways and thirteen upward transitions, into `lvl_end` (the chapter's last
room, whose ending is a cutscene). Every entity in these rooms is in the model
(zip movers, falling, crumble and dash blocks, refills, springs; fake walls
are not solid), so the rooms can also be searched with the entities the TAS
does not touch.

`lvl_9` needed one rule that is not in the published `Player.cs`: a climb
jump off a zip mover starts it (for that frame the climb jump counts as
riding the solid she jumped off, like climbing it; the 1.4 code seems to call
this `climbTriggerDir`). There the TAS climb-jumps off the zip mover's side
on frame 44 and rides it much later; its inputs work only if the zip mover
starts on exactly that frame (tried by starting it by hand on every frame
from 1 to 67). "Grabbing next to a wall starts it even when she cannot
climb" would fit the TAS equally well; the model uses the climb jump.

`python3 tools/celestetas.py community lvl_1 lvl_end --entities ZipMover FallingBlock
CrumblePlatform DashBlock --dump celeste-sat-community-1a.txt -o community-1a.tas`
writes the whole community `1A.tas` recording every frame of the chapter;
`tests/recordings.py` checks such a recording room by room and shows the
first frame that differs. It would check the rooms from `lvl_5` on frame by
frame (not recorded yet); it cannot tell the two climb-trigger rules apart,
since in the TAS both start the zip mover on the same frame (the model has
the other one as `-DCLIMB_TRIGGER_GRAB` for a probe that does).

**Can the TAS leave a room sooner?** (`experiments/tas_endings.py`) For every
room of the chained TAS: keep its inputs up to 10 frames before it leaves,
and ask CBMC whether any inputs get out one frame sooner (one query per
room, 20 s to 14 min).

| room | TAS leaves on | one frame sooner, last 10 frames free | the next room's TAS inputs after that ending |
|---|---|---|---|
| `lvl_1` | 92 | no | |
| `lvl_2` | 118 | **117** | fail (`lvl_3`) |
| `lvl_3` | 107 | **106** | fail (`lvl_4`: in the game too, see below) |
| `lvl_4` | 91 | **90** | fail (`lvl_3b`) |
| `lvl_3b` | 98 | **97** | fail (`lvl_5`) |
| `lvl_5` | 139 | no | |
| `lvl_6` | 117 | no | |
| `lvl_6a` | 161 | no | |
| `lvl_6b` | 110 | no | |
| `lvl_6c` | 110 | no | |
| `lvl_7` | 103 | no | |
| `lvl_8` | 107 | **106** | fail (`lvl_8b`) |
| `lvl_8b` | 99 | no | |
| `lvl_9` | 97 | no | |
| `lvl_9b` | 73 | no | |
| `lvl_10a` | 204 | no | |
| `lvl_11` | 161 | no | |
| `lvl_12` | 147 | **146** | fail (`lvl_12a`) |
| `lvl_12a` | 141 | no | |

Where a room can be left sooner, the TAS leaves it later on purpose: in a
state the next room's route is built on (`lvl_8` leaves with a jump at
−105 px/s rather than falling; `lvl_12` dashes up-right rather than
right; `lvl_2` keeps its wall speed retention). The faster endings are
worth something only if the next room can make up for the state it gets,
which `experiments/tas_crossings.py` (`tools/cross.py` at each room change) asks
next: can she be in the TAS's exact state a few frames into the next room,
one frame sooner? With the room's last 6 frames and the next room's first 3
free (one query per frame she could leave on, 15–40 min per room change),
so far: `lvl_1` → `lvl_2`, `lvl_2` → `lvl_3` and `lvl_3` → `lvl_4`: no
(proven). The Leonardo campaign ran all 18 room changes
(`hpc/crossings.sbatch`, `results/leonardo/cross/`), with the last 6 frames
of the first room and 3 of the next free, and again with 10 and 8: **all 36
proven**. No change around any room transition of the TAS gets into the
next room's TAS state sooner.

Frames of control per room, each room entered the way the community TAS
enters it (room 1 from the spawn):

| room | community TAS (real game) | SAT on the TAS's ending | this project's own search (beam + polish) |
|---|---|---|---|
| `lvl_1` | 92 | nothing faster once frames 1–80 are fixed (2 min) | 99 |
| `lvl_2` | 118 | **117** once frames 1–106 are fixed (6 min); 116 impossible (3 min) | 125 |
| `lvl_3` | 107 | **106** once frames 1–95 are fixed (3 min); 105 impossible (3 min) | 133 |

The project's own search is well behind the TAS: the beam search's rollouts
steer towards the exit and do not discover lines like the climb jump out of a
dash in room 1, or the speed the TAS carries into room 3. Its 99-frame room 1
route (`results/routes/1a_lvl_1.tas`) relies on a 5 px ceiling correction while
dashing straight up (frame 96), a rule that was inferred and that the
recording of the route in the game confirms. What the SAT solver adds is on
the TAS's own routes:

- `lvl_3`, 106, **confirmed in the game**: the TAS dashes up through the
  exit gap and leaves after the dash ends (−120 px/s). A jump on the dash's
  last frame, 4–5 px from the gap's left edge, is a wallbounce (−160 px/s):
  out one frame sooner. The community `1A.tas` with the last line of
  `#lvl_3` (`16,U,X`) replaced by `4,U,X` / `1,U` / `9` / `1,J`, recorded in
  Celeste 1.4, leaves `lvl_3` on frame 106, every frame as the model says. It
  relies on the wallbounce reaching 5 px (v1.2.3.0); at 3 px it would not
  exist. But it is probably not a frame for the chapter: the community TAS
  opens `lvl_4` with a wallbounce off the left wall on its first frame, which
  needs the `lvl_3` up-dash still dash-attacking and Madeline 4 px from that
  wall. The 106-frame ending spends the dash on its own wallbounce and enters
  `lvl_4` 3 px further right with no dash attack left, and the TAS's `lvl_4`
  inputs then die on spikes on frame 60, in the game as in the model (a
  recording). Like `lvl_2` below, the TAS gives up a frame in one room to set
  up the next.
- `lvl_2`, 117 (model only so far): wallbounce one frame later and go
  straight up. But the TAS's slower-looking ending is deliberate: it ends
  with a wall jump that leaves 211 px/s of wall speed retention pending,
  which carries through the transition, so `lvl_3` starts with two climb
  jumps at full speed. The 117-frame ending loses that, and the TAS's
  `lvl_3` inputs no longer work. Likewise the beam search found a 114-frame
  `lvl_2` (dash up the shaft 20 frames earlier), after which our best
  `lvl_3` is 127 frames.

So rooms have to be optimised together; see [methods.md](methods.md#across-room-boundaries).

From the rooms' spawn points (standing, in control), the beam search and
polish find 99, 115 and 126 frames (`results/routes/1a_lvl_*.tas`). Before the model
had two keys per button and the changes since the published `Player.cs`,
they were 102, 144 and 126, and the first room's "proof" was about a weaker
game.

## The Leonardo campaign (October 2026)

About 2,300 core-hours on CINECA's Leonardo Booster (`hpc/`). The output is
in `results/leonardo/` (provenance: commit 9e3dd4f, CBMC 5.80.0; Chapter 1's
model is unchanged from it to now). `python3 hpc/summary.py` tallies it:

| window proofs over the chained community TAS | windows | proven ("no") | timeouts | "faster" |
|---|---|---|---|---|
| W = 12, all 19 rooms | 2,028 | 2,022 | 2 | 4 |
| W = 16, all 19 rooms | 1,819 | 1,804 | 4 | 11 |
| W = 18, `lvl_1` | 73 | 73 | 0 | 0 |

**What the proofs say.** For 3,899 windows: no input sequence gets from the
TAS's state at frame K to its state at frame K + W + 1 (on the compared
fields) in W frames or fewer, within the model. That is the local-optimality
certificate (Tier B).

**What the "faster" windows are not.** All 15 sit at the end of a room
(`lvl_6a` K = 139-143, `lvl_12` K = 126-133, `lvl_3b` K = 80/84, `lvl_9b`
K = 53). The window harness counts leaving the room as success, so each one
is a faster *ending*: the room is left 2-5 frames sooner **in a different
state**. They are the same kind of result as the TAS endings above. None
of them is a chapter saving. `tools/splice_tas.py combine` finds none that
keeps the exit state, and with every one of them the next room's TAS inputs
fail (`experiments/next_room.py`):

| faster ending | leaves on | next room with the TAS's inputs |
|---|---|---|
| `lvl_6a` (5 windows) | 156-159 instead of 161 | `lvl_6b` dies (frame 35-97) or never leaves |
| `lvl_12` (W = 12, 3 windows) | 143-145 instead of 147 | `lvl_12a` dies (frame 60-61) |
| `lvl_3b` (2 windows) | 96 instead of 98 | `lvl_5` never leaves |
| `lvl_9b` (1 window) | 70 instead of 73 | `lvl_10a` never leaves |

Each could still pay off if the next room can be re-routed from the new
entry to make the frames back. That is the seam problem ([ROADMAP.md](../ROADMAP.md), step 6),
not a result yet. `tools/windows.py` now marks each YES as "same exit state"
or "different exit state".

**The real lead: `lvl_6a` in 118 frames.** The beam-search sweep, polishing
the TAS's own route from the TAS's entry into the room, found a 118-frame
`lvl_6a` (the TAS takes 161). It climbs the narrow shaft at the left and
runs along *above* the room's top edge (y ≈ −2 to −6; with no room above, the
game only stops her 24 px above it, and the model treats the space outside
the room as empty) before dropping into the open area. It replays from the
TAS's entry, not from the room's spawn. From the new exit,
`hpc/candidate_checks.sbatch` found a 137-frame `lvl_6b` (TAS 110): 255
frames for the two rooms against 271. But the TAS's `lvl_6c` inputs fail
after that `lvl_6b`, and the best `lvl_6c` found from there so far is ~154
frames (TAS 110). So the route is not yet faster over the chapter, and the
`lvl_6a` route itself has not been played in the game. A 43-frame shortcut
in a room humans have optimised for years means either the game stops her
somewhere the model doesn't, or the shortcut is real. `test_through_6b_logged.tas`
(commit 2af9286) plays the chapter from the start with this `lvl_6a` while
recording; its recording (`dump_6a_6b.txt`) answers that.

## Chapter 2: the Badeline chase

The chase (rooms 3 to 12 of 2A) is in the model: dream blocks, Badeline
chasers, switch gates, touch switches and invisible barriers. It is in the
differential fuzzer too. Each room starts from the state the previous one
leaves her in (`tools/chain_chapter2.py`), the chasers' history included.

**Everything in this section predates the dream-block fix of 2026-10-13**
([history.md](history.md#2026-10-13-the-first-chapter-2-recording-and-ilspy)).
The first recording of the chase found that the model moved her on the
frame a dash enters a dream block and saw her leave a frame late. The routes
below were found with that timing, and in the fixed model
`results/routes/2a_chase.tas` dies in `2a_lvl_4`. They are kept as the
record of what was found and are being solved again.

| room | `results/routes/2a_chase.tas` | community TAS |
|---|---|---|
| `2a_lvl_3` | 102 | (cutscene skip) |
| `2a_lvl_4` | 117 | 110 |
| `2a_lvl_5` | 146 | 116 |
| `2a_lvl_6` | 222 | 198 |
| `2a_lvl_7` | 252 | 221 |
| `2a_lvl_8` | 213 | 188 |
| `2a_lvl_9` | 267 | 234 |
| `2a_lvl_10` | 628 | 633 |
| `2a_lvl_2` | 158 | 152 |
| `2a_lvl_11` | 130 | 110 |
| `2a_lvl_12b` | 169 | 134 |
| `2a_lvl_12` | 127 | 125 |
| rooms 4-12 | 2,429 | 2,221 |

- `results/routes/2a_chase.tas` (and `results/celestetas/2a_chase.tas` to
  play it): 12 rooms, 2,531 frames of control, found on 2026-10-01. It
  replayed exactly in the model until the dream-block fix. Its recording in
  the game (2026-10-13) is what found the bug.
- `results/celestetas/2a_chase_rooms_3_to_7.tas`: rooms 3-7 in 833 frames
  (`2a_lvl_5` 141, `2a_lvl_7` 251), with the old timing too. Its `2a_lvl_7` exit
  doesn't lead into the 12-room route's `2a_lvl_8` (the chasers are
  elsewhere).
- Between commit 1d3e148 and 2026-10-12 the model had a different
  touch-switch hitbox ([verification.md](verification.md#chapter-2-one-recording-so-far)),
  under which neither route replayed. The Leonardo chase run (beam width
  500,000; rooms 3-9 in 105, 117, 141, 222, 245, 207 and 102 frames, then a
  failure in `2a_lvl_10` that led to the exit fix of 588c008) used that
  hitbox, so its routes need re-solving. They are not in the repository.

## Chapter 1, room 1 (`lvl_1`) in the community TAS

How the community TAS crosses the first room in 92 frames, frame by frame in
the model (`build/chain_tas/lvl_1/sim -v build/chain_tas/lvl_1/route.tas`
after running `tests/chain_tas.py`):

- **1–6**: dash right from the spawn; the dash moves on frame 5; jump on
  frame 6 while the dash is still on the ground = super, 260 px/s.
- **17–20**: jump presses in the air are kept 5 frames; she lands on the first
  pillar at the end of frame 19 and jumps off it on frame 20.
- **27–40**: up-right dash. A dash never lowers a faster horizontal speed, so
  she keeps 211 px/s and reaches the side of the big block on frame 40.
- **41**: jump + grab while the dash is still running, facing the block: a
  climb jump out of the dash (v1.2.2.4). With the old model this was a wall
  jump away from the block, and the route fell apart here.
- **49–53**: on top of the block, dash with Down held, so she ducks; the dash
  takes its direction on frame 53 (right), and the jump on that same frame is
  a super while ducked = hyper, 325 px/s.
- **60**: jump off the block's edge at 332 px/s.
- **73–76**: at the wall, jump pressed again with the second key while held,
  plus grab: a climb jump with no direction held. Pressing left on frame 75
  is a wall boost: the stamina comes back and she is thrown left at 130 px/s,
  lined up with the gap in the ceiling.
- **77–92**: dash up; a corner correction moves her 2 px into the gap on
  frame 88; on frame 92 a jump off the gap's edge, still dash-attacking, is a
  wallbounce (−160 px/s), and she is out.


## Demo rooms

| room | beam route | SAT: "can she leave one frame sooner?" | answer | time |
|---|---|---|---|---|
| `ledge` (7×6 tiles) | 18 frames, 2 s | frames 1–12 fixed (5 free) | no | 19 s |
| | | frames 1–8 fixed (9 free) | no | 86 s |
| | | frames 1–4 fixed, i.e. only "dash on frame 1" (13 free) | no | 17 min |
| | | nothing fixed, leave within 10 frames | no | 4 min |
| `hop` (10×8 tiles) | 21 frames, 3 s | frames 1–12 fixed (8 free) | no | 61 s |
| | | frames 1–8 fixed (12 free) | no | 4 min |

(Times from the first model, without climbing or the second keys. With
everything modelled the answers so far are the same and the queries take
longer: `ledge` 33 s (5 free) and 204 s (9 free), `hop` 144 s (8 free) and 435 s (12 free).)

So in `ledge`, once dash is pressed on frame 1, **18 frames is optimal** in the
first model: no dash direction, super, hyper or later input does better. With
the full model (second keys, crouch dash, v1.4 rules) it is proven only once
frames 1–8 of the saved route are fixed -- and the full model has a
**17-frame route** that also dashes on frame 1 and leaves the saved route at
frame 5 (`results/routes/ledge_17.tas`, found by the beam search at rollout
10, identical in both builds). Whether 16 is possible is open; it is the
cheapest full-room proof in the project (see the roadmap).

The `ledge` route (`results/routes/ledge.tas`):

```
   1,L,X      dash (direction is read later, so L does nothing)
   3          freeze frames
  14,R,J      frame 5: jump while grounded in the dash = super (260 px/s);
              frame 10: hits the ledge face, speed stored for 4 frames;
              frame 14: clears the ledge top, 234 px/s restored; exits on frame 18
```
