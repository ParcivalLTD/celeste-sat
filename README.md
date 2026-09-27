# celeste-sat

Find the fastest way through a Celeste room with a SAT solver, and prove when
nothing faster exists.

Madeline's movement is ported frame-for-frame from Celeste's published
`Player.cs` (github.com/NoelFB/Celeste, MIT licence) to C. The same C code is
used three ways: a simulator that replays inputs, a beam search that finds fast
routes, and a CBMC harness where every frame's input is a free variable and a
SAT solver searches (or proves there is nothing to find).

```
python3 tools/solve.py rooms/ledge.txt --from-frame 8
```

```
beam: exit on frame 18 (2.1s)
upper bound: 18 frames (beam search)
keeping frames 1..8 fixed; the solver optimises frames 9..
SAT: can she leave by frame 17? (9 free frames) ... no -> 18 is optimal (86s)
```

## Requirements

gcc, python3 and CBMC (`apt install cbmc`; tested with 5.95.1, which uses
MiniSat). Nothing else.

## Layout

| path | what it is |
|---|---|
| `model/celeste.h`, `model/celeste.c` | the port: normal + dash states, collisions, freeze frames, input buffers |
| `tools/gen_tables.c` | computes the exact timer frame counts with the game's float arithmetic |
| `tools/make_room.py` | ASCII room → `room.h` |
| `tools/import_map.py` | lists the rooms in a Celeste map file (`Content/Maps/*.bin`) and exports one to ASCII |
| `sim/sim.c` | replays a CelesteTAS-style file, prints a per-frame trace, dumps mid-run states |
| `search/beam.c` | beam search over the exact model (upper bounds in seconds) |
| `harness/solve.c` | the CBMC harness |
| `tools/solve.py` | the pipeline: build → beam → SAT descent → replay check → tidy → `best.tas` |
| `tools/render.py` | builds the replay page from solved rooms |
| `tests/diff.sh` | differential fuzzing of the two builds, with mechanic coverage |
| `rooms/*.txt` | demo rooms (`#` solid, `.` air, `S` spawn; exit = open tiles on the right edge) |

## How the pipeline works

1. **Beam search** (`search/beam.c`) keeps the best 50,000 distinct states per
   frame, scored by distance to the exit after a short rollout (so states in the
   middle of a dash freeze are not thrown away). It returns a real route, which
   is an upper bound U.
2. **SAT descent** asks CBMC: *is there any input sequence that leaves the room
   by frame U−1?* A counterexample is a faster route; it is replayed in the
   simulator (the two must agree) and the question is asked again. When CBMC
   answers "VERIFICATION SUCCESSFUL", no route of that length exists, so the
   current best is optimal within the model.
3. `--from-frame K` holds the first K frames fixed and makes everything after
   them free. The proof then says: *given this opening, nothing is faster.*
   This is how long rooms become tractable (see "Scaling").
4. **Tidy** replaces inputs after frame K with simpler ones (continue the
   previous input, hold right, or nothing) wherever that does not cost a frame.
   The route stays just as fast and becomes readable.

## What the model covers

Modelled from `Player.cs` and the Monocle engine:

- running, air control, friction, ducking, duck correction
- jumps: coyote time, variable jump height, half gravity at the apex, fast fall
- dashes: 8 directions read on the first frame after the freeze, the 3 freeze
  frames, speed retention, dash slides, dash end speeds, refills and cooldowns
- supers (including on the first dash frame), hypers, wall jumps, super wall jumps
  (wallbounces), wall slides, wall speed retention
- upward and dash corner correction, dash floor snapping, falling unduck
- `Input.Jump` / `Input.Dash` 0.08 s buffers (5 frames), press edges
- room bounds: leaving through the right edge is the goal, falling out is death

Not modelled yet: grabbing and climbing (stamina), all entities (spikes, springs,
jump-throughs, moving blocks, boosters, feathers, dream blocks…), water, wind,
lift speed, holdables, assist modes. `MAX_DASHES` is 1.

### Fidelity details

- `DeltaTime` is `(float)TimeSpan.FromTicks(166667).TotalSeconds` = `0.0166667f`
  (XNA/FNA's fixed 60 fps step), not 1/60.
- Every float operation keeps the C# order, so single-precision rounding matches.
  Where C# multiplies constants inside a branch (`RunAccel * mult * DeltaTime`),
  the port picks between the two fully-constant products, which is bit-identical
  and lets CBMC fold them.
- `Actor.MoveH` rounds the subpixel counter with `Math.Round` (ties to even),
  then steps pixel by pixel and calls the collision callback.
- Monocle's `StateMachine`/`Coroutine` timing is reproduced: the dash coroutine
  reaches `yield return null` in the frame the dash starts, runs its body on the
  first frame after the freeze, then waits `DashTime` (the float countdown lasts
  9 frames, so a dash moves for 10).
- The solver build replaces float timers with integer frame counters computed by
  `gen_tables.c` using the same float arithmetic (coyote time is 6 frames, the
  input buffer 5, freeze 3, dash cooldown 12 …). It also moves straight to the
  single tile boundary a ≤ 8 px move can cross instead of stepping pixel by
  pixel, and reads collisions from an 8×8-tile window around the player.
  `tests/diff.sh` runs both builds on 30 random rooms × 300 random input runs:
  **3.2 million frames, bit-identical**, with every mechanic above exercised
  (from 204 duck corrections to 479,000 wall-slide frames).

### Things to check against the real game

The port has only been checked against itself. Before trusting a route, replay
it in the game with [CelesteTAS](https://github.com/EverestAPI/CelesteTAS):

- `Player.cs` in the repo is from 2018; the current game (1.4) may differ.
- Float results can differ between the old 32-bit XNA build (x87 registers) and
  64-bit builds (SSE). The port matches strict IEEE single precision, which is
  what Everest's .NET Core builds use.
- The room start is "standing at the spawn, in control". A real room is entered
  with the speed and timers of the previous room, and a respawn plays an
  intro animation first.
- The level transition condition (hitbox right edge past the room edge, hitbox
  inside the room vertically) is written from memory of `Level.EnforceBounds`.

To build a test room in the game, recreate the ASCII layout in Lönn (1 character
= 1 tile = 8 px), put Madeline's spawn on the `S` tile, and add a room to the right.

## Results

| room | beam route | SAT: "can she leave one frame sooner?" | answer | time |
|---|---|---|---|---|
| `ledge` (7×6 tiles) | 18 frames, 2 s | frames 1–12 fixed (5 free) | no | 19 s |
| | | frames 1–8 fixed (9 free) | no | 86 s |
| | | frames 1–4 fixed, i.e. only "dash on frame 1" (13 free) | no | 17 min |
| | | nothing fixed, leave within 10 frames | no | 4 min |
| `hop` (10×8 tiles) | 21 frames, 3 s | frames 1–12 fixed (8 free) | no | 61 s |
| | | frames 1–8 fixed (12 free) | no | 4 min |

So in `ledge`, once dash is pressed on frame 1, **18 frames is optimal**: no dash
direction, super, hyper or later input does better. The proof over every
possible opening (17 free frames) is the next step; start it with
`tools/solve.py rooms/ledge.txt --tas results/ledge.tas --timeout 36000`.

The `ledge` route (`results/ledge.tas`):

```
   1,L,X      dash (direction is read later, so L does nothing)
   3          freeze frames
  14,R,J      frame 5: jump while grounded in the dash = super (260 px/s);
              frame 10: hits the ledge face, speed stored for 4 frames;
              frame 14: clears the ledge top, 234 px/s restored; exits on frame 18
```

The beam search found the super on the first dash frame and the use of wall
speed retention without being told about either.

## Scaling

Times are CBMC 5.95 + MiniSat on one core.

| question | free frames | answer | time |
|---|---|---|---|
| flat room, exit within N frames | 2 / 4 / 6 / 10 | no | 1.6 s / 8.9 s / 26 s / 190 s |
| `ledge`, exit within N frames | 8 / 10 | no | 88 s / 230 s |
| `ledge`, exit within 18 frames (a solution exists) | 18 | – | stopped after 25 min |

Each extra frame multiplies proof time by roughly 1.5. The formula is about
250,000 variables per frame (about half collision checks, the rest single-precision
arithmetic). A CDCL solver has no arithmetic reasoning: to rule out "exit in 10
frames" on an open floor, it has to rediscover through bit-level adders that
speeds are bounded. Kissat and CaDiCaL were no faster than MiniSat here, and
Bitwuzla/Z3 on the same formula matched or lost.

Exhaustive search is no better: the number of *distinct* states grows about
4× per frame (1.8 million by frame 8), because different input timings leave
different subpixels.

So the practical recipe is the hybrid above: the beam search for a strong route,
then SAT on windows of 8 to 13 free frames, where it either finds an improvement
or proves the window optimal.

### Ideas for going further

- **Lower bounds by abstraction.** Prove "cannot exit before frame L" on a
  coarser model (fixed-point speeds, nondeterministic rounding) where SAT is
  fast, and refine only where it finds a spurious route. If L meets the best
  route, the whole room is proven.
- **Sliding windows (large neighbourhood search).** Fix everything except a
  window of ~10 frames, let SAT improve it, slide the window.
- **Cube and conquer.** Split on the discrete skeleton (which frame each dash
  starts on, whether it is cancelled) and solve the cubes in parallel.
- **Cheaper collisions.** Precompute each frame's local collision features once
  instead of ~50 separate hitbox checks.
- **Real rooms.** `tools/import_map.py` reads Celeste's map files
  (`Content/Maps/*.bin`) and exports a room's tiles and spawn to the ASCII
  format. Most vanilla rooms still need mechanics the model lacks: exits
  upward, spikes, jump-throughs, springs, zip movers.
