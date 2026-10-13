# Verification: the model against the game

Three independent checks keep the model honest:

1. **The two builds against each other.** `tests/diff.sh` runs the literal
   reference build (float timers, pixel-by-pixel movement) and the solver
   build (frame counters, boundary-jump movement, the 8x8 collision window)
   on random rooms and random inputs and compares every frame bit for bit,
   and checks every rule the SAT harnesses rely on (symmetry breaking,
   dominance, `same_future`). See [model.md](model.md#fidelity-details).
2. **The community TAS.** Played in the real game, its inputs finish the
   chapter; replayed in the model, each room's inputs must leave that room
   on exactly their last frame (`tests/chain_tas.py`).
3. **Recordings from the real game.** CelesteTAS's `ExportGameInfo` records
   Madeline's exact position, speed and state every frame; the model must
   give the same numbers (`tests/recordings.py data/recordings`).


## Checked against the real game

**The community TAS.** [VampireFlower/CelesteTAS](https://github.com/VampireFlower/CelesteTAS)
holds the tool-assisted speedrun inputs for every chapter; played in the
real game with CelesteTAS, they finish it. `python3 tests/chain_tas.py`
downloads the Chapter 1 file (at a fixed commit), and plays each room's
inputs through the model, each room from the state the previous one left
Madeline in. The first four rooms, as first checked:

| room | community inputs | model leaves the room on frame |
|---|---|---|
| `lvl_1` (from the spawn) | 92 frames | 92 |
| `lvl_2` (entered from `lvl_1`) | 118 frames | 118 |
| `lvl_3` (entered from `lvl_2`) | 107 frames | 107 |
| `lvl_4` (entered from `lvl_3`, a zip mover) | 91 frames | 91 |

It goes on through the whole chapter: all 19 rooms, 2,275 frames of
control, every room left on its last frame (the table is in
[results.md](results.md#chapter-1-in-the-model)).

A room's inputs only lead out of it on their last frame if every frame before
agrees with the game: the routes use supers on the first dash frame, climb
jumps out of dashes, crouch-dash hypers, the jump-through platforms, climbing,
a corner correction and a wallbounce, and they press Jump again while holding
it (two keys). Before this project's model had the two keys and the
changes listed above, the first room's inputs did not even get out of it.

**A recording.** The [celeste-rl](https://github.com/shihaab453/celeste-rl) project recorded
a 376-frame input sequence (walking, grabbing, jumping, dashing) played in
the real game from Chapter 1's first room into the second, with Madeline's
exact state at a few frames (their `tests/fixtures/env_replies.json`,
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
record Madeline's position, speed and state on every frame. The recordings
are in `data/recordings/`. Each recording's own inputs, replayed in the
model, give the same numbers on every frame:

| recording | frames compared | what it settles |
|---|---|---|
| `results/routes/1a_lvl_1.tas`, room 1 from the spawn | 99, identical; leaves on frame 99 in both | the 5 px ceiling correction while dashing straight up (frame 96, inferred) is real |
| `results/routes/1a_lvl_3.tas`, room 3 from the spawn | 126, identical; leaves on frame 126 | |
| `probe_dash_cooldown.tas`: a super cancels a dash, then dash pressed every frame | 30, identical; dashes again on frame 16 | the dash cooldown is 0.2 s, not the 0.15 s of the 1.2.5.0 changelog |
| `probe_1a_lvl_1_to_2.tas`: a 102-frame room 1 route, then nothing pressed | 102 in room 1, identical; then 50 in room 2 from the model's entry state, identical | the room transition upwards: where she stops, her speed and automatic jump, and that control returns 41 frames after the exit frame |
| the community TAS's `#lvl_3`, entered as in the TAS | 107, identical | |
| the same with the 106-frame ending (below) | 106, identical; leaves on frame 106 | the wallbounce reaches 5 px (v1.2.3.0, inferred); the TAS's room 3 can be a frame faster |
| the community TAS from `#lvl_4` to `#lvl_5`, with the zip mover | `lvl_4` 91, identical, leaves on frame 91 in both; `lvl_3b` 98, identical, leaves on frame 98 | falling unducking waits for coyote time to end (`lvl_4`, frames 55–67); the upward stop point in `lvl_4`, `lvl_3b` (9 px) and `lvl_5` (5 px) |
| the same after the 106-frame `#lvl_3` ending (below) | `lvl_4`: 59 identical, dies on spikes on frame 60 in both | after that ending the TAS's `lvl_4` inputs fail, in the game as in the model |
| seven probes (`experiments/make_up_probes.py`): room 1 left at y = 0–5, dashing, ducking or neither | 93–96 in room 1, identical; 17–22 in room 2 | going up into a 184 px room she always stops 9 px above its bottom edge |

`python3 tests/recordings.py data/recordings` repeats the check for every
recording, room after room (`tools/run_tests.sh --vanilla` runs it); point it
at the Celeste folder, where CelesteTAS writes them, to check new ones
(`tools/run_tests.sh --vanilla --recordings DIR`).


## Checking a route in the game

`tools/celestetas.py` compares the model with the real game frame by frame,
using [CelesteTAS](https://github.com/EverestAPI/CelesteTAS-EverestInterop)
(needs Everest). `results/celestetas/` has ready files:

1. Play one in Celeste Studio, e.g. `results/celestetas/1a_lvl_1.tas`. It
   loads the room (`console load 1 lvl_1`), waits for the respawn animation,
   then plays the route inside `ExportGameInfo`, which records Madeline's
   exact position (pixel + subpixel), speed and state every frame to a text
   file in the Celeste folder.
2. Compare:
   `python3 tools/celestetas.py compare rooms/vanilla/1a_lvl_1.txt results/routes/1a_lvl_1.tas celeste-sat-1a_lvl_1.txt`

It reports how many frames agree and shows the first frame that differs;
`--start ENTRY.h` starts the room from an entry state instead of the spawn.
For other routes: `tools/celestetas.py export ROOM ROUTE --load "1 lvl_2" -o
check.tas`. `tests/recordings.py` (above) checks all recordings in a folder
at once, from the inputs they record.

For rooms of the community TAS, `tools/celestetas.py community lvl_4 lvl_3b
-o check.tas` writes the whole `1A.tas` with a recording of those rooms (and
of the zip movers: `--entities`), optionally with a changed ending
(`--replace 'lvl_3:16,U,X=4,U,X/1,U/9/1,J'`); `tests/recordings.py` checks
the result from the entry state `tests/chain_tas.py` computes.


## Chapter 2 in the game

The Badeline chase (rooms 3 to 12 of 2A, `rooms/vanilla/2a_*.txt`, exported
by `tools/import_chapter2.py` from `2-OldSite.bin`) is solved room after room,
each from the state the previous one leaves her in, and played in the game as
one recorded file:

```
python3 tools/chain_chapter2.py                     # build/chapter2_chase/2A_chase.tas
python3 tools/celestetas.py chain build/chapter2_chase/2A_chase.tas --load "2 3" --skip-cutscene \
    --dump celeste-sat-2a-chase.txt -o results/celestetas/2a_chase.tas
```

`results/celestetas/2a_chase.tas` is that file for the 12-room route in
`results/routes/2a_chase.tas`, which replays in the current model
(`tools/run_tests.sh` checks it). It is ready to record.

`chain` replays every room in the model first (each must be left on its last
frame), then writes: `console load 2 3` (the game's room names drop the map's
`lvl_` prefix), 300 idle frames, a pause and Skip Cutscene, 60 idle frames,
and every room's inputs with the 40 idle frames of each room transition, all
inside `ExportGameInfo`. Play the file in Celeste Studio, then `python3 tests/recordings.py <folder with celeste-sat-2a-chase.txt>`
checks it room by room (recordings named `celeste-sat-2a-*` are checked
against the 2A rooms).

## Things still to check

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
  variable (4 by default); the recording of `results/routes/1a_lvl_1.tas` confirms
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
- Room transitions (`celeste_sat/transition.py`): the parts in `Player.cs`
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

### Chapter 2 (nothing recorded yet)

Everything Chapter 2 adds rests on the game's code as read, the differential
fuzzer and the demo-room checks (`tests/test_chapter2.py`), and none of it on
a recording. In order of how much a route depends on it:

- **Touch switches.** The model checks the switch's 30 × 30
  `PlayerCollider` (±15 px around it) against her hurtbox (bottom 2 px above
  her feet). Two sources back that. The published `Player.cs` swaps in the
  hurtbox for the whole `PlayerCollider` loop of `Update`. MaxHelpingHand's
  `FlagTouchSwitch`, a mod that mirrors the vanilla switch, builds
  `new PlayerCollider(onPlayer, null, new Hitbox(30f, 30f, -15f, -15f))` next
  to a 16 × 16 entity `Collider`. Commit 1d3e148 had switched the model to the
  16 × 16 box against her collider. That reads the entity's `Collider` where
  the `PlayerCollider`'s own box applies, so it was reverted on 2026-10-12.
  With the revert, the 12-room chase route of 2026-10-01 replays again
  (under the 16 × 16 box it died in `2a_lvl_6`). Chapter 2 results computed
  between the two (the Leonardo chase run) have to be redone. A recording of
  a switch room (`2a_lvl_6`) would settle it for good, and so would two
  minutes in ILSpy: open `Celeste.exe`, go to `Celeste.TouchSwitch`'s
  constructor and read the `PlayerCollider` it adds. Until then the other
  reading is one flag away: `-DTOUCH_ENTITY_COLLIDER` (in Python,
  `build(room, bdir, start, defines=["TOUCH_ENTITY_COLLIDER"])`).
  Replaying the community 2A TAS through the model doesn't decide it yet. The
  TAS's inputs stop working in `2a_lvl_4` with either hitbox, before any
  switch room. That finding matters by itself (ROADMAP, step 3).
- **The chaser.** Its delay (1.55 s plus 0.4 s per chaser, read three frames
  wide because of `Scene.TimeActive` rounding), its 6 × 6 hitbox at (−3, −7),
  the wake-up delay after a respawn (`CHASER_WAKE`, 6 frames in the model,
  "at least 8" in the game) and that its history runs on across rooms with
  the transition's 40 frames standing at the entry.
- **Dream blocks.** `DREAM_DASH_MIN_TIME`, the speed and the exits (with a
  jump, into a climb, into a solid with the ±5 px wiggle).
- **Switch gates.** The timing of `SwitchGate.Sequence()` (it starts moving
  46 updates after the last switch, arrives after 165).

One recording of the chase settles most of this the way the `lvl_4`
recording settled falling-unduck in Chapter 1.
