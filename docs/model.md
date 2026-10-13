# The model

What `model/celeste.c` ports, how it stays bit-exact with the game's single
precision, and how each entity beyond `Player.cs` is modelled. What is still
inferred rather than checked is in [verification.md](verification.md#things-still-to-check).


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
- invisible barriers (`InvisibleBarrier`): a solid that never moves and is
  never drawn, used in the game to close an opening off. Static, so it needs
  nothing in the state, in `same_future` or in the room transition -- only a
  box among the moving solids, after which every solid check sees it. They are
  not assumed to be tile-aligned.
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
current code for the rest, listed in [verification.md](verification.md#things-still-to-check).

Not modelled yet: every other entity (wall springs, two-dash refills, other
moving platforms, … none of them in Chapter 1's rooms on the TAS's way), wind,
water, holdables, climb blockers, assist modes. `MAX_DASHES` is 1.


## Fidelity details

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
  third, dash blocks in every fifth, dream blocks in every fourth, invisible
  barriers in every third, a Badeline chaser or two in every fifth, and a
  switch gate with its touch switches where a zip mover slot is free) × 300
  random input runs: **2.95 million frames, bit-identical**, with every
  mechanic above exercised (riding, pushing and squishing included; falling and
  crumble blocks set off hundreds of times, dash blocks broken, dream blocks
  entered 431 times and ending in a solid 271 of those — 103 wiggling out of
  it, 168 fatally —, barriers blocking her 51,456 times, touch switches hit 981
  times, switch gates opening 395 times, chasers catching her 1,484 times).

  The Chapter 2 mechanics were added to this fuzzing after the fact, and it
  immediately found two bugs in them, both on the frame a dream dash ends: a
  player killed by dream-dashing into a solid went on to run the ordinary
  movement code from inside that solid (which the solver build's boundary-jump
  movement does not model), and the ±5 px wiggle of
  `Player.DreamDashedIntoSolid` used a solid check that excluded dream blocks,
  so it could leave her standing inside one. Both are fixed; the wiggle now
  uses the same `CollideCheck<Solid>` as the game, which counts dream blocks.
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
  keep agreeing on everything `same_future` compares. 6.8 million checks, none
  broken. The Chapter 2 fields are in it: the dream dash's two are compared
  only in `ST_DREAM_DASH` (both are set on entering it), and of the chaser's
  256 recorded positions only those inside the longest chase delay, since no
  chaser can read an older one. `harness/cross.c` is given room B's entity
  counts (`tools/cross.py` copies them out of the generated `room_b.h`): it
  includes `celeste.h` rather than `celeste.c`, so without them every entity
  comparison in `same_future` would compile away silently.


## Zip movers

`ZipMover.cs`, `Solid.cs`, `Platform.cs` and `Actor.cs` are not published;
this follows their decompiled behaviour as remembered, and the parts in
`Player.cs` (lift boost, riding) as published. What is not yet checked
against a recording is listed in [verification.md](verification.md#things-still-to-check).

- **Path.** `ZipMover.Sequence()` waits for a rider (`HasPlayerRider`), waits
  0.1 s, moves to its target in 0.5 s (`Calc.Approach(at, 1, 2 * dt)`,
  `Ease.SineIn`, `Vector2.Lerp`, `Platform.MoveTo`), waits 0.5 s, moves back
  in 2 s, waits 0.5 s, and starts over when someone rides it then.
  ``celeste_sat/room_header.py` replays that coroutine once, in single precision
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
  and walking off (`NormalUpdate`: a rising platform gives its speed). The
  grace time does not run during a room transition (her updates stop), so a
  lift speed can carry into the next room; a room entered like that is built
  with the lift code too (`CARRIED_LIFT`, which `celeste_sat/build.py` and
  `tools/cross.py` set). None of the TAS's room changes carries one.
- **Speed bounds.** The SAT harnesses assume |speed| ≤ 400 × 250 px/s
  (1000 × 400 with lift boosts) as redundant facts that help the solver;
  a start state carrying more (a room entered fast from the one before:
  `lvl_9b` at 654 px/s) raises them to its own speeds, so that the
  assumption never cuts off a real route.
- **Cost.** In rooms without zip movers all of this compiles away: the
  formula for `ledge` is within 0.05 % of what it was before. Rooms with them
  allow whole-pixel moves up to 16 px (the rounding comparisons and the
  movement split accordingly), and rooms up to 64 tiles tall.


## Falling blocks

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
  (then it is no longer solid). ``celeste_sat/room_header.py` replays the fall in
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
the model (see [results.md](results.md#chapter-1-in-the-model)).


## Chapter 2: dream blocks, Badeline, switch gates

What the Chapter 2 rooms need, from the game's code (`Celeste.exe`,
disassembled):

- **The intro cutscene.** `BadelineOldsite.Added` starts `CS02_BadelineIntro`
  in room 3 until the session flag `evil_maddy_intro` is set, so a
  `console load 2 3` plays it. Skipped, `OnEnd` leaves her where she stood,
  in the normal state, **facing left** (`; spawn 120 168 -1`), with
  `JustRespawned` set.
- **Badeline.** Each chaser (`darkChaser`, index i in the room) follows the
  positions the player recorded (`Player.ChaserStates`) from
  1.55 s + 0.4 s × i ago (`GetChasePosition`), approaching them at 500 px/s,
  and kills her when its 6 × 6 hitbox at (−3, −7) touches her hurtbox. After a
  respawn it waits until she moves. Its delay runs in game time, across rooms:
  the transition's 40 frames count, so in the next room the chasers first
  replay the end of the previous one and then wait at her entry point.
  The model keeps her last 256 positions (`celeste_sat/transition.py` carries them into
  the next room) and checks the frames 91–93 (+24 × i) back, since which one
  "1.55 s ago" picks depends on the rounding of `Scene.TimeActive`.
- **Switch gates** (rooms 6, 7, 9, 10). `TouchSwitch`: its own
  16 × 16 box against her hurtbox (its `PlayerCollider` has no box of its
  own; the 30 × 30 one is for feather flight); when every switch in the room is on they all finish at
  once. `SwitchGate.Sequence()`: `yield 0.1 s`, the icon spin-up
  (`Rate += 2 dt` per frame to 1), `yield 0.1 s`, then a 2 s `Ease.CubeOut`
  tween to its node (`Platform.MoveTo`), updated from the next frame. It is
  modelled as a zip mover of kind 1 (`ZIP_KIND`): tables from `gate_cycle`
  in `celeste_sat/room_header.py`; it starts moving 46 updates after the last switch
  and arrives after 165. The beam search aims for the switches it still
  needs (in the best order) before the exit.
