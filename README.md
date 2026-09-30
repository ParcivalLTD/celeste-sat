# celeste-sat

Find the fastest way through a Celeste room with a SAT solver, and prove when
nothing faster exists.

Madeline's movement (normal, climb and dash states) is ported frame-for-frame
to C from Celeste's published `Player.cs` (github.com/NoelFB/Celeste, MIT
licence), brought up to the current game (v1.4) with the movement changes
listed in the official changelogs since that file was published. The same C
code is used three ways: a simulator that replays inputs, a beam search that
finds fast routes, and a CBMC harness where every frame's input is a free
variable and a SAT solver searches (or proves there is nothing to find).

```
python3 tools/solve.py rooms/ledge.txt --from-frame 8
```

```
beam: exit on frame 18 (0.7s)
upper bound: 18 frames (beam search)
keeping frames 1..8 fixed; the solver optimises frames 9..
SAT: can she leave by frame 17? (9 free frames) ... no -> 18 is optimal (204s)
```

It also runs on rooms from the game itself, and it agrees with the game: the
community TAS of Chapter 1 (played in the real game) replays in the model
room after room, each room's inputs leaving that room on exactly their last
frame, and routes found here, recorded in Celeste 1.4 with CelesteTAS, match
the model in every frame, subpixels included (see "Checked against the real
game"). A query can also span a room
transition, since the fastest way out of one room is not always the fastest
way through the next (see "Across room boundaries").

## Requirements

gcc, python3 and CBMC (`apt install cbmc`; tested with 5.95.1, which uses
MiniSat). Nothing else. On Windows, use WSL (Ubuntu).

To build and check everything on your machine:

```
bash tools/run_tests.sh                    # fuzz both builds, replay saved routes, beam on demo rooms
bash tools/run_tests.sh --vanilla --sat    # also Chapter 1 rooms 1-3 and short SAT checks (one across a room transition)
```

## Layout

| path | what it is |
|---|---|
| `model/celeste.h`, `model/celeste.c` | the port: normal, climb and dash states, collisions, freeze frames, input buffers, spikes, refills, zip movers, falling, crumble and dash blocks, lift boost, room transitions |
| `tools/gen_tables.c` | computes the exact timer frame counts with the game's float arithmetic |
| `tools/make_room.py` | ASCII room → `room.h` (with each zip mover's path and falling block's fall, computed in single precision) |
| `tools/import_map.py` | lists the rooms in a Celeste map file (`Content/Maps/*.bin`) and exports one to ASCII |
| `sim/sim.c` | replays a CelesteTAS-style file, prints a per-frame trace, dumps mid-run states |
| `sim/tas_io.h` | reads and writes CelesteTAS-style input files (two keys per button) |
| `search/beam.c` | beam search over the exact model (upper bounds in seconds to minutes) |
| `harness/solve.c` | the CBMC harness |
| `harness/input_rules.h` | the rules on free inputs shared by the harnesses (symmetry breaking, dominance) |
| `harness/cross.c`, `sim/chain.c`, `tools/cross.py` | SAT across a room transition: two rooms in one query (see "Across room boundaries") |
| `harness/window.c`, `tools/windows.py`, `sim/live.c` | SAT on every window of a known route: can that stretch be done a frame faster? (see "Windows inside a route") |
| `model/transition.h`, `model/state_eq.h` | the room transition in C, and "these two states have the same future" |
| `tools/solve.py` | the pipeline: build → beam → polish → SAT descent → replay check → tidy → `best.tas` |
| `tools/render.py` | builds the replay page from solved rooms |
| `tests/diff.sh` | differential fuzzing of the two builds, with mechanic coverage and symmetry checks |
| `tests/community_tas.py` | replays the community TAS of Chapter 1 through the model, rooms 1–4 |
| `tests/chain_tas.py` | the same through the whole chapter (rooms exported from the map as it goes), as far as the model goes |
| `tests/tas_endings.py` | SAT on the end of each room of the chained TAS: can she leave it a frame sooner? |
| `tests/recordings.py` | checks recordings from the game (CelesteTAS `ExportGameInfo`) frame by frame, room after room |
| `tests/make_up_probes.py` | CelesteTAS files that record upward room transitions left in different ways |
| `tests/real_game.py` | replays a recording from the real game (celeste-rl) and compares Madeline's state |
| `tools/run_tests.sh` | builds and checks everything on your machine |
| `tools/celestetas.py` | writes CelesteTAS files for routes and compares the game's recording with the model |
| `tools/chapter.py` | solves rooms in sequence, each starting in the state the previous one left her in |
| `tools/transition.py` | the entry state for the next room from a dumped exit state (what `tools/chapter.py` does between rooms) |
| `rooms/*.txt` | demo rooms (`shaft_a` and `shaft_b` are stacked, for the cross-room check) |

## Room format

One character per 8×8 tile: `#` solid, `.` air, `S` spawn, spikes as
`^` `v` `<` `>` (the direction they point; the tile is air and the spikes sit
on the neighbouring solid face) and `-` for a jump-through platform along the
top of the tile. Directives:

```
; exit up 240 560        the goal: a neighbouring room above, covering x in [240, 560)
; leave down -240 80     a neighbouring room that is not the goal (going there = failing)
; spawn 19 144           exact spawn in pixels (overrides S)
; spikes left 272 80 16  spikes in the game's entity coordinates
; jumpthru 8 160 40      a jump-through platform, top edge at y = 160, x in [8, 48)
; spring 120 144         a floor spring, base centre at (120, 144)
; zipmover 112 80 24 16 184 72   a zip mover: top-left (112, 80), 24 x 16, moving to (184, 72)
; refill 152 72         a dash refill centred at (152, 72)
; fallingblock 152 160 32 24 1   a falling block: top-left (152, 160), 32 x 24; 1 = climbing it sets it off too
; crumble 232 152 24    a crumble block: top-left (232, 152), 24 x 8
; dashblock 304 240 24 32 1   a dash block, 24 x 32; 1 = a dash breaks it
```

Without an `exit` line the whole right edge is the exit. Spikes and springs
act in the order they are listed, as in the game.

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

## What the model covers

From `Player.cs` and the Monocle engine:

- running, air control, friction, ducking, duck correction
- jumps: coyote time, variable jump height, half gravity at the apex, fast fall
- dashes: 8 directions read on the first frame after the freeze, the 3 freeze
  frames, speed retention, dash slides, dash end speeds, refills and cooldowns
- supers (including on the first dash frame), hypers, wall jumps, super wall jumps
  (wallbounces), wall slides, wall speed retention
- grabbing and climbing: climb up/down, slipping off the top, stamina, climb
  jumps, wall boosts (the stamina refund), climb hops over ledges, and grab wall slides
- upward and dash corner correction, dash floor snapping, falling unduck
- the 0.08 s (5-frame) input buffers of Jump, Dash and Crouch Dash
- spikes in all four directions (`Spikes.OnCollide`, checked with the hurtbox;
  touching spikes also blocks the ground dash refill and climb hops)
- jump-through platforms: landing from above, standing (refills, coyote time),
  the jump-through assist that lifts her through when rising inside one, the
  sideways-dash nudge onto them, and dash floor snapping onto them
- floor springs (`Player.SuperBounce`: back on top of the spring, dash and
  stamina refilled, 185 px/s up with automatic variable jump, horizontal speed
  zeroed)
- room bounds (`Level.EnforceBounds`): leaving through an edge that has a
  neighbouring room is the goal, other edges are walls (the top one 24 px
  above the room), falling out is death
- refills (one dash): taken when she touches one (16 × 16) while a dash is
  missing or stamina is below 20 (`Player.UseRefill`); taking one refills
  stamina, freezes the game for 0.05 s like a dash, and the refill is back
  after 2.5 s
- zip movers (see "Zip movers" below): a solid that starts when she stands
  on it or climbs it, carries her along its path and pushes her out of its
  way; the lift boost it leaves her (`Player.LiftBoost` in jumps, supers,
  wall jumps, wallbounces, dashes, letting go of a wall, walking off it),
  kept for 0.16 s after she leaves it
- falling blocks (see "Falling blocks" below): a solid that shakes when she
  stands on it or climbs it, waits while she stays, falls (carrying or
  crushing her) and lands or drops out of the room; spikes on a zip mover or
  falling block move with it
- crumble blocks (`CrumblePlatform`): standing on one, it shakes for 0.2 s
  and then goes as soon as she leaves it or 0.4 s later; climbing it, it goes
  after 1 s whatever she does; it is back after 2 s, once she is out of its
  way (same code as the moving solids, so from memory of the decompiled
  source too)
- dash blocks: a solid that a dash breaks (still dash-attacking, moving the
  way she dashed: `DashBlock.OnDashed`), bouncing her back
  (`Player.Rebound`: 120 px/s away from it, 120 px/s up, 0.15 s of
  variable jump); fake walls are not solid and change nothing

Inputs are those of the game with its default bindings, as CelesteTAS writes
them: directions, Grab (held), and Jump, Dash and Crouch Dash with **two keys
each** (J/K, X/C, Z/V). A button counts as pressed on any frame where one of
its keys goes down, so it can be pressed again on the very next frame without
being released (pressing the other key). Every TAS relies on this; with a
single key, pressing again costs a frame of release, which ends a variable
jump.

Changes to the game after the published `Player.cs`, from the official
changelogs (celestegame.com/changelog.html):

| version | change | how it is ported |
|---|---|---|
| 1.2.2.4 | "You can now perform a climb jump from the Dash state" | in `DashUpdate`, a jump at a wall while facing it and holding Grab is a climb jump |
| 1.2.2.4 | "You can now hyper jump from coyote time" | a dash that starts while Down is held (or with Crouch Dash) starts ducked, on the ground or not |
| 1.2.3.0 | "maximum distance from a wall that the player can wall jump" 3 → 5 px | 5 px for wallbounces (straight-up dash, still dash-attacking) unless spikes face her there; 3 px otherwise |
| 1.2.3.0 | ceiling corner correction 4 → 5 px | 5 px while dash-attacking with no horizontal speed, 4 px otherwise |
| 1.4.0.0 | Crouch Dash button | a dash that starts ducked |
| 1.4.0.0 | dash corner correction, the dash jump-through nudge and the dash floor snap no longer move her onto spikes | skipped when her hurtbox would touch spikes at the corrected spot; the horizontal dash corner correction also only moves around a corner (the tile behind the free spot must be solid) |
| (not in a changelog) | falling unducking waits for the end of coyote time | found with a recording: in `lvl_4` the community TAS walks off a ledge ducked, jumps in coyote time and stays ducked under a wall; the published code would stand her up as she starts to fall |

The exact form of these rules comes from three places: the community TAS,
whose room 1 inputs only work with the climb jump out of a dash and the
ducking dash; mods that patch these methods and quote or match the current
code (Extended Variant Mode, GravityHelper), for the 5 px wallbounce reach,
the variable ceiling correction reach and the spike checks; and memory of the
current code for the rest, listed under "Things to check".

Not modelled yet: every other entity (wall springs, two-dash refills, other
moving platforms, … none of them in Chapter 1's rooms on the TAS's way), wind,
water, holdables, climb blockers, assist modes. `MAX_DASHES` is 1.

### Fidelity details

- `DeltaTime` is `(float)TimeSpan.FromTicks(166667).TotalSeconds` = `0.0166667f`
  (XNA/FNA's fixed 60 fps step), not 1/60.
- Every float operation keeps the C# order, so single-precision rounding matches.
  Where C# multiplies constants inside a branch (`RunAccel * mult * DeltaTime`),
  the port picks between the two fully-constant products, which is bit-identical
  and lets CBMC fold them. Stamina is a float, updated exactly as in the game.
- `Actor.MoveH` rounds the subpixel counter with `Math.Round` (ties to even),
  then steps pixel by pixel and calls the collision callback.
- Monocle's `StateMachine`/`Coroutine` timing is reproduced: the dash coroutine
  reaches `yield return null` in the frame the dash starts, runs its body on the
  first frame after the freeze, then waits `DashTime` (the float countdown lasts
  9 frames, so a dash moves for 10).
- The solver build replaces float timers with integer frame counters computed by
  `gen_tables.c` using the same float arithmetic (coyote time is 6 frames, the
  input buffer 5, freeze 3, dash cooldown 12, climb no-move 6, climb hop 12,
  wall boost window 12 …). It also moves straight to the single tile boundary
  a ≤ 8 px move can cross instead of stepping pixel by pixel, and reads
  collisions from an 8×8-tile window around the player.
  `tests/diff.sh` runs both builds on 40 random rooms (with spikes, jump-throughs,
  springs, exits on all sides, zip movers in every other room and falling
  blocks, some with spikes on them, in the others, crumble blocks in every
  third, dash blocks in every fifth) × 300 random input runs: **3.02 million
  frames, bit-identical**, with every mechanic above exercised (riding,
  pushing and squishing included; falling and crumble blocks set off
  hundreds of times, crumble blocks coming back 300 times, dash blocks
  broken 151 times).
- The harness never lets the solver choose an input that cannot matter, which
  keeps the formula small: directions and Grab during freeze frames, Up outside
  climbing and the dash-direction frame, Grab away from walls, a second-key
  press of a button that was not held. It also skips presses that could only
  fill an input buffer: since a press is possible on any frame (two keys), a
  press whose buffer would be used later can move to the frame where it is
  used. So Dash and Crouch Dash are pressed only on a frame where a dash starts,
  and Jump is pressed again while held only where that jumps. The fuzzing
  checks every such rule on every random frame: the barred input must give the
  identical state (or, for the buffer rules, differ only in the buffer).
  2.0 million checks, none broken.
- The cross-room queries compare states with `same_future`
  (`model/state_eq.h`), which ignores fields that can no longer matter (the
  value behind an expired timer, the previous frame's aim, …). The fuzzing
  checks that too: on every random frame it scrambles those fields in a copy,
  runs both on with the same random inputs for up to 40 frames, and they must
  keep agreeing on everything `same_future` compares. 7.0 million checks, none
  broken.

### Zip movers

`ZipMover.cs`, `Solid.cs`, `Platform.cs` and `Actor.cs` are not published;
this follows their decompiled behaviour as remembered, and the parts in
`Player.cs` (lift boost, riding) as published. What is not yet checked
against a recording is listed under "Things to check".

- **Path.** `ZipMover.Sequence()` waits for a rider (`HasPlayerRider`), waits
  0.1 s, moves to its target in 0.5 s (`Calc.Approach(at, 1, 2 * dt)`,
  `Ease.SineIn`, `Vector2.Lerp`, `Platform.MoveTo`), waits 0.5 s, moves back
  in 2 s, waits 0.5 s, and starts over when someone rides it then.
  `tools/make_room.py` replays that coroutine once, in single precision
  like the game (sub-pixel movement counter, `Math.Round` to even), and writes
  one table entry per update: its position, the whole pixels it moved, and the
  `LiftSpeed` of that move (`moveH / DeltaTime`, `moveV / DeltaTime`). The
  state keeps one counter per zip mover (0 = waiting, else updates since it
  started), so the solver sees a table lookup, not trigonometry. For the one
  in `lvl_4` (24 × 16 at (112, 80), to (184, 72)) the trip out is 30 updates,
  starting 8 updates after she lands on it; the whole cycle is 219.
- **Update order.** After a room transition the player entity comes before
  the new room's entities, so each frame the zip movers update after her:
  they see where her update left her, and she sees their lift on her next
  update. (A room loaded from scratch, e.g. `console load`, puts her after
  them; that order is not modelled.)
- **Riding and pushing** (`Solid.MoveHExact` / `MoveVExact`): standing on it
  (`Actor.IsRiding`: 1 px below her feet) or climbing it (`Player.IsRiding`:
  1 px in front) carries her with each whole-pixel move; if the move runs
  into her she is pushed out of the way. Either way she gets its
  `LiftSpeed`. A push she cannot follow (a wall behind her) is a squish,
  counted as death (`Player.OnSquish` ducks or wiggles out when it can; not
  modelled). Also ported: moving sideways, a zip mover pushes a player who
  runs the same way just above its top edge 1 px down.
- **Lift speed** (`Actor.LiftSpeed`): set by a carry or push, cleared by her
  next `Actor.Update` (after her state machine, before her movement); the last
  non-zero value stays readable for `LiftSpeedGraceTime` (0.16 s = 10
  frames). `Player.LiftBoost` caps it (|x| ≤ 250, −130 ≤ y ≤ 0) and adds it to
  jumps, supers and hypers (before the ducking multipliers), wall jumps,
  wallbounces, dash starts, letting go of a wall or running out of stamina,
  and walking off (`NormalUpdate`: a rising platform gives its speed).
- **Cost.** In rooms without zip movers all of this compiles away: the
  formula for `ledge` is within 0.05 % of what it was before. Rooms with them
  allow whole-pixel moves up to 16 px (the rounding comparisons and the
  movement split accordingly), and rooms up to 64 tiles tall.

### Falling blocks

`FallingBlock.cs` is not published either; this follows its decompiled
behaviour as remembered. The zip mover's solid code (boxes, riding, pushing,
squishing, lift speed, climb hops onto it) is shared: both are "moving
solids" (`CUR_MS_BOX` in `model/celeste.c`).

- **Sequence** (`FallingBlock.Sequence()`, one counter `fbT` per block):
  it waits until she stands on it, or (climbFall, the default) climbs it;
  shakes for 0.2 s (12 updates); then, for up to 0.4 s (24 updates), waits
  while she still stands on it, climbs it or touches its sides; then falls:
  `speed = Approach(speed, 160, 500 * dt)`, `MoveVCollideSolids(speed * dt)`,
  until it lands on the tiles or a jump-through, or is 16 px below the room
  (then it is no longer solid). `tools/make_room.py` replays the fall in
  single precision and writes one table entry per update: its position, the
  whole pixels moved and its `LiftSpeed` (a downward lift boosts nothing, so
  without zip movers in the room it is not tracked). Blocks landing on other
  moving solids are not modelled (the export refuses such rooms).
- **Spikes on it** (`Spikes` attach to a solid they touch from outside,
  `StaticMover`) move with it. This applies to zip movers too (`lvl_9` has
  spikes on one).
- **Cost.** The formula for `lvl_7` (two blocks) is about 28 % larger than
  the same room without them.

The community TAS's `lvl_7` sets both of its blocks off and plays exactly in
the model (see "Real rooms").

### Checked against the real game

**The community TAS.** [VampireFlower/CelesteTAS](https://github.com/VampireFlower/CelesteTAS)
holds the tool-assisted speedrun inputs for every chapter; played in the
real game with CelesteTAS, they finish it. `python3 tests/community_tas.py`
downloads the Chapter 1 file (at a fixed commit), takes the inputs of the
first four rooms and plays them through the model, each room from the state
the previous one left Madeline in:

| room | community inputs | model leaves the room on frame |
|---|---|---|
| `lvl_1` (from the spawn) | 92 frames | 92 |
| `lvl_2` (entered from `lvl_1`) | 118 frames | 118 |
| `lvl_3` (entered from `lvl_2`) | 107 frames | 107 |
| `lvl_4` (entered from `lvl_3`, a zip mover) | 91 frames | 91 |

`tests/chain_tas.py` goes on through the chapter as far as the model goes
(all 19 rooms, see "Real rooms").

A room's inputs only lead out of it on their last frame if every frame before
agrees with the game: the routes use supers on the first dash frame, climb
jumps out of dashes, crouch-dash hypers, the jump-through platforms, climbing,
a corner correction and a wallbounce, and they press Jump again while holding
it (two keys). Before this project's model had the two keys and the
changes listed above, the first room's inputs did not even get out of it.

**A recording.** The [celeste-rl](https://github.com/shihaab453/celeste-rl) project recorded
a 376-frame input sequence (walking, grabbing, jumping, dashing) played in
the real game from Chapter 1's first room into the second, with Madeline's
exact state at a few frames (`tests/fixtures/env_replies.json`,
`room1_exit_dash_route`). Replaying the same inputs in the model:

| after frame | real game | model |
|---|---|---|
| 27 | (32, 144) + 0.38893688 px, dash state | (32, 144) + 0.3889369 px, dash state |
| 32 | (38, 138) + (0.045802, 0.343135) px, speed (169.70563, −169.70563) | identical |
| 265 | (273, 32) − 0.47223556 px, speed −45.83342, ducking, on ground | identical |
| 285 | leaves room 1 for room 2 | leaves on frame 285 |

Same pixels, same subpixels, same frame of the room transition after 285
frames of random play. `python3 tests/real_game.py` downloads the recording
and repeats the check.

**Recordings of this project's routes.** Played in Celeste 1.4.0.0 (Everest
1.6580.0, CelesteTAS 3.47.1) with the files in `results/celestetas/`, which
record Madeline's position, speed and state on every frame. Each recording's
own inputs, replayed in the model, give the same numbers on every frame:

| recording | frames compared | what it settles |
|---|---|---|
| `results/1a_lvl_1.tas`, room 1 from the spawn | 99, identical; leaves on frame 99 in both | the 5 px ceiling correction while dashing straight up (frame 96, inferred) is real |
| `results/1a_lvl_3.tas`, room 3 from the spawn | 126, identical; leaves on frame 126 | |
| `probe_dash_cooldown.tas`: a super cancels a dash, then dash pressed every frame | 30, identical; dashes again on frame 16 | the dash cooldown is 0.2 s, not the 0.15 s of the 1.2.5.0 changelog |
| `probe_1a_lvl_1_to_2.tas`: a 102-frame room 1 route, then nothing pressed | 102 in room 1, identical; then 50 in room 2 from the model's entry state, identical | the room transition upwards: where she stops, her speed and automatic jump, and that control returns 41 frames after the exit frame |
| the community TAS's `#lvl_3`, entered as in the TAS | 107, identical | |
| the same with the 106-frame ending (below) | 106, identical; leaves on frame 106 | the wallbounce reaches 5 px (v1.2.3.0, inferred); the TAS's room 3 can be a frame faster |
| the community TAS from `#lvl_4` to `#lvl_5`, with the zip mover | `lvl_4` 91, identical, leaves on frame 91 in both; `lvl_3b` 98, identical, leaves on frame 98 | falling unducking waits for coyote time to end (`lvl_4`, frames 55–67); the upward stop point in `lvl_4`, `lvl_3b` (9 px) and `lvl_5` (5 px) |
| the same after the 106-frame `#lvl_3` ending (below) | `lvl_4`: 59 identical, dies on spikes on frame 60 in both | after that ending the TAS's `lvl_4` inputs fail, in the game as in the model |
| seven probes (`tests/make_up_probes.py`): room 1 left at y = 0–5, dashing, ducking or neither | 93–96 in room 1, identical; 17–22 in room 2 | going up into a 184 px room she always stops 9 px above its bottom edge |

`python3 tests/recordings.py DIR` repeats the check for every
`celeste-sat-*.txt` and `community-*.txt` recording in DIR (the Celeste
folder, where CelesteTAS writes them), room after room; `tools/run_tests.sh
--vanilla --recordings DIR` includes it.

### Checking a route in the game

`tools/celestetas.py` compares the model with the real game frame by frame,
using [CelesteTAS](https://github.com/EverestAPI/CelesteTAS-EverestInterop)
(needs Everest). `results/celestetas/` has ready files:

1. Play one in Celeste Studio, e.g. `results/celestetas/1a_lvl_1.tas`. It
   loads the room (`console load 1 lvl_1`), waits for the respawn animation,
   then plays the route inside `ExportGameInfo`, which records Madeline's
   exact position (pixel + subpixel), speed and state every frame to a text
   file in the Celeste folder.
2. Compare:
   `python3 tools/celestetas.py compare rooms/vanilla/1a_lvl_1.txt results/1a_lvl_1.tas celeste-sat-1a_lvl_1.txt`

It reports how many frames agree and shows the first frame that differs;
`--start ENTRY.h` starts the room from an entry state instead of the spawn.
For other routes: `tools/celestetas.py export ROOM ROUTE --load "1 lvl_2" -o
check.tas`. `tests/recordings.py` (above) checks all recordings in a folder
at once, from the inputs they record.

For rooms of the community TAS, `tools/celestetas.py community lvl_4 lvl_3b
-o check.tas` writes the whole `1A.tas` with a recording of those rooms (and
of the zip movers: `--entities`), optionally with a changed ending
(`--replace 'lvl_3:16,U,X=4,U,X/1,U/9/1,J'`); `tests/recordings.py` checks
the result from the entry state `tests/community_tas.py` computes.

### Things to check against the real game

What is still inferred rather than taken from code or checked against the game
(settled by the recordings above: the 0.2 s dash cooldown, which the 1.2.5.0
changelog gives as 0.15 s; the upward room transition):

- The wallbounce reach: mods confirm a 5 px distance in `WallJumpCheck`
  besides the usual 3; that it applies while dash-attacking after a
  straight-up dash is now confirmed by the 106-frame `lvl_3` ending. That
  spikes facing her there turn it off is still from memory.
- The ceiling corner correction reaches 5 px when she is dash-attacking with
  no horizontal speed (read as |Speed.X| < 0.01; left is tried when
  Speed.X ≤ 0.01, right when Speed.X ≥ −0.01). Mods confirm that the reach is a
  variable (4 by default); the recording of `results/1a_lvl_1.tas` confirms
  a 5 px correction to the right during a straight-up dash. The exact
  condition (and the left side) is from memory.
- Spike checks for dash corrections use her normal hurtbox (8 × 9) at the
  corrected position, against spikes of any direction; the dash floor snap
  tests the full 3 px.
- Supers from dashes: only while `DashDir.Y == 0` (horizontal dashes, or
  before the dash has a direction), as in the published code. One mod's
  comment calls the check "DashDir.Y < 0.1", which would also allow supers out
  of upward dashes during coyote time; the community TAS does not tell them
  apart.
- Only `Player.cs` is published. `Actor` movement, jump-throughs, springs,
  spikes (`Spikes.cs`), `Level.EnforceBounds` and `MapData.CanTransitionTo`
  are written from memory of the game's behaviour: spike hitboxes are 3 px
  strips, up spikes kill when `Speed.Y >= 0` and the hurtbox bottom is not
  below the spike base, the other
  directions when moving into them; transitions test the point 8 px (sideways)
  or 12 px (up/down) beyond the player's centre. Celeste 1.4 decides whether a
  climb hop is blocked by up spikes more finely (by the spike sprites). The
  community TAS exercises most of this in rooms 1–3.
- Room transitions (`tools/chapter.py`): the parts in `Player.cs`
  (`BeforeUpTransition`, `TransitionTo`, `OnTransition`) are ported. Going
  up, recordings settle where she stops: 9 px above the new room's bottom
  edge in rooms 184 px tall (`lvl_2`, `lvl_4`, `lvl_3b`, with seven different
  ways of leaving `lvl_1`), 5 px in `lvl_5` (288 px); the community TAS's
  rooms entered from below work only with 5 px in `lvl_7` (216 px), and
  with it in `lvl_10a`, `lvl_12` and `lvl_11` (224, 232 and 264 px). 5 px
  is what a 4 px pad inside the room gives (the rule sideways and downwards
  too); why rooms one screen plus 4 px tall get 9 is not known. Sideways and downwards the stop point is
  inferred (4 px inside the edge she crossed, 12 px when falling in); the
  chapter chain goes through three sideways transitions exactly.
- Tiles outside the room count as air. In the game they belong to the
  neighbouring rooms; this only matters if Madeline's hitbox pokes out of the
  room somewhere other than an exit.
- Float results can differ between the old 32-bit XNA build (x87 registers) and
  64-bit builds (SSE). The port matches strict IEEE single precision, which is
  what Everest's .NET Core builds use.
- Zip movers and falling blocks (checked only through the community TAS
  playing exactly: `lvl_5`, `lvl_6b`, `lvl_7`, `lvl_8`; the `lvl_4` recording
  does not ride its zip mover): the coroutines' waits and moves as described
  above; that the player updates before a room's entities after a
  transition; that `Platform.Update` clears a
  platform's `LiftSpeed` after its coroutine has moved it, so a wall jump off
  a zip mover (`Player.WallJump` reads the wall's `LiftSpeed` when her own is
  zero) gets nothing from it (`-DZIP_WALL_LIFT` switches to the other
  reading); `Actor.LiftSpeedGraceTime` = 0.16 s; the published `WallJump`
  looks for that wall 3 px to her right whatever the direction.
  `results/celestetas/` has no zip mover probe yet; recordings made with
  `ExportGameInfo, <file>, ZipMover` also record its position, and
  `tests/recordings.py` prints it next to the model's at the first difference.

## Real rooms

`tools/import_map.py` reads the map files of your own copy of the game
(`Content/Maps/*.bin`, Celeste's BinaryPacker format) and exports a room with
its tiles, spawn, exits (one per neighbouring room) and spikes:

```
python3 tools/import_map.py "<Celeste>/Content/Maps/1-ForsakenCity.bin"          # list rooms
python3 tools/import_map.py "<Celeste>/Content/Maps/1-ForsakenCity.bin" lvl_1 -o rooms/vanilla/1a_lvl_1.txt
python3 tools/solve.py rooms/vanilla/1a_lvl_1.txt --polish --from-frame 85
```

Extracted rooms stay out of git (`rooms/vanilla/` is ignored). Other entities
are listed in the export as "NOT MODELLED". `--to lvl_3` makes the room above
the goal; going back down to `lvl_1` then counts as failing.

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

`results/celestetas/celeste-sat-community-1a.tas` is the whole community
`1A.tas` recording every frame of the chapter (with zip movers, falling
blocks, crumble and dash blocks); `tests/recordings.py` checks it room by
room and shows the first frame that differs. It would check the rooms from
`lvl_5` on frame by frame, and settle which of the two rules is the game's.

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
route (`results/1a_lvl_1.tas`) relies on a 5 px ceiling correction while
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

So rooms have to be optimised together; see "Across room boundaries" below.

From the rooms' spawn points (standing, in control), the beam search and
polish find 99, 115 and 126 frames (`results/1a_lvl_*.tas`). Before the model
had two keys per button and the changes since the published `Player.cs`,
they were 102, 144 and 126, and the first room's "proof" was about a weaker
game.

### Windows inside a route

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

### Rooms in sequence

In a real run each room starts the way the previous one ended. For an upward
exit the game sets her speed to (0, −105) with an automatic full jump,
refills dash and stamina, puts the dash on a 0.2 s cooldown, zeroes the
subpixels and moves her up into the new room until her feet are 9 px above
its bottom edge (5 px in rooms taller than 184 px, see "Things to check");
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

### Across room boundaries

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
`tools/chapter.py`), and there is one query per frame she could leave A on,
run in parallel (`--jobs`). `--exit-from F` skips the frames before F when a
single-room proof has already ruled them out.

The check in `tools/run_tests.sh --sat`: two stacked demo rooms, `shaft_a`
and `shaft_b`, and a route that waits one frame too long before dashing up
out of `shaft_a` (`tests/shaft_a.tas`, 11 + 10 frames). CBMC finds the
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

### Chapter 1, room 1 (`lvl_1`) in the community TAS

How the community TAS crosses the first room in 92 frames, frame by frame in
the model (`build/community_tas/lvl_1/sim -v route.tas` after running
`tests/community_tas.py`):

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

## Results (demo rooms)

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

So in `ledge`, once dash is pressed on frame 1, **18 frames is optimal**: no dash
direction, super, hyper or later input does better (proven with the first
model; with the full model, second keys and crouch dash included, it is
proven so far once frames 1–8 are fixed).

The `ledge` route (`results/ledge.tas`):

```
   1,L,X      dash (direction is read later, so L does nothing)
   3          freeze frames
  14,R,J      frame 5: jump while grounded in the dash = super (260 px/s);
              frame 10: hits the ledge face, speed stored for 4 frames;
              frame 14: clears the ledge top, 234 px/s restored; exits on frame 18
```

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

### Ideas for going further

- **Lower bounds by abstraction.** Prove "cannot exit before frame L" on a
  coarser model (fixed-point speeds, nondeterministic rounding) where SAT is
  fast, and refine only where it finds a spurious route. If L meets the best
  route, the whole room is proven.
- **Waypoints.** Split a long room at states every route must pass (the top
  of a block, a gap) and prove each part.
- **Cube and conquer.** Split on the discrete skeleton (which frame each dash
  starts on, whether it is cancelled) and solve the cubes in parallel.
- **Cheaper collisions.** Precompute each frame's local collision features once
  instead of ~50 separate hitbox checks.
- **Across room boundaries, further.** The SAT windows over a transition
  (`tools/cross.py`) need the next room's state to match exactly. Comparing
  endings that leave different states (room 2's 114/117/118) needs the next
  room solved well from each; a beam search over the chained rooms, ranked by
  progress through both, would do it once the beam is strong enough.
- **More entities.** Zip movers, crumble blocks, refills and dash blocks would
  open the rest of Chapter 1, and the community TAS would check each of them
  the way it checked rooms 1–3.
- **A better rollout.** The beam search's lookahead runs, jumps and climbs
  towards the exit, supers on a dash's first frame on the ground and climb
  jumps out of dashes at walls, but it never dashes or wall-boosts on its
  own, and those are what the TAS routes are built from.
