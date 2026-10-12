# celeste-sat

A frame-exact model of Madeline's movement in *Celeste*, written in C and
checked against the real game down to the subpixel. A beam search uses it to
find speedrun routes, and a SAT solver uses it to prove when a stretch of a
route can't be done any faster.

The same C code runs three ways. It is a **simulator** that replays inputs, a
**beam search** that finds fast routes, and a **CBMC harness** in which every
frame's input is a free variable. In the harness the SAT solver either finds
a faster route or proves that none exists, within the model.

```
$ python3 tools/solve.py rooms/ledge.txt --tas results/routes/ledge.tas --from-frame 8
upper bound: 18 frames (results/routes/ledge.tas)
keeping frames 1..8 fixed; the solver optimises frames 9..
SAT: can she leave by frame 17? (9 free frames) ... no -> 18 is optimal (224s)
```

## What it has shown

- **The model reproduces the game.** The community TAS of Chapter 1
  ([VampireFlower/CelesteTAS](https://github.com/VampireFlower/CelesteTAS))
  replays in the model room after room: 19 rooms, 2,275 frames of control,
  with zip movers, falling, crumble and dash blocks, refills and springs.
  Each room's inputs leave that room on exactly their last frame. Fifteen
  recordings made in Celeste 1.4 with CelesteTAS match the model on every
  frame, subpixels included.
- **The model agrees with itself.** A literal port (float timers,
  pixel-by-pixel movement) and the optimised build the solver uses agree bit
  for bit on 2.95 million fuzzed frames in random rooms. Every shortcut the
  SAT harness takes is fuzzed as well.
- **SAT finds frames the human TAS left.** Chapter 1's room 3 can be left
  one frame sooner (107 → 106) with a wallbounce on the dash's last frame.
  The game confirms it, although that ending costs the next room the setup
  it was built on. SAT queries also prove that no change to the last 10
  frames of 13 of the 19 rooms saves a frame, and neither does any change
  around the first three room transitions (within the frames tested).
- **Certificates at scale.** A campaign on the EuroHPC supercomputer
  Leonardo (~2,300 core-hours) ran ~4,300 window proofs over the whole
  community TAS of Chapter 1. Each one shows that no 12- or 16-frame stretch
  of the route can be shortened to reach the same state. The campaign
  reported 15 frames that *can* be saved in the model. Those results are
  being committed, and none of the savings has been played in the game yet
  ([ROADMAP.md](ROADMAP.md), steps 1-2).
- **Chapter 2** (the Badeline chase) is modelled: dream blocks, Badeline
  chasers, switch gates and invisible barriers, all in the fuzzer. A 12-room
  chase route (2,531 frames) plays in the model. None of it has been checked
  against the game yet.

"Proven" here always means *within the model*, and usually *given the frames
before the window*. What can and can't be claimed is in
[docs/methods.md](docs/methods.md#what-proven-means).

## Quick start

Linux or WSL with `gcc`, `python3` and [CBMC](https://github.com/diffblue/cbmc)
5.95 (`sudo apt install -y gcc python3 cbmc`). Nothing else.

```bash
bash tools/run_tests.sh                            # unit tests, fuzzing, saved routes, demo rooms (no game needed)
python3 tools/solve.py rooms/ledge.txt --polish    # beam search, then SAT: can it be done a frame faster?
```

Running the game's own rooms needs your copy of the game. Copy its map files
into `game/` ([game/README.md](game/README.md)):

```bash
cp "<Celeste>/Content/Maps/1-ForsakenCity.bin" game/
python3 tests/chain_tas.py                         # the community TAS through all of Chapter 1, in the model
bash tools/run_tests.sh --vanilla --sat            # + recordings from the game and SAT checks
```

## Documentation

| | |
|---|---|
| [ROADMAP.md](ROADMAP.md) | where the project stands, and the plan towards a record, a paper and a release |
| [docs/model.md](docs/model.md) | what is ported, how floats stay bit-exact, every entity |
| [docs/verification.md](docs/verification.md) | the checks against the real game, how to record a route, what is still unverified |
| [docs/methods.md](docs/methods.md) | the pipeline: beam search, SAT descent, windows, queries across room transitions; scaling; what "proven" means |
| [docs/results.md](docs/results.md) | all measurements: Chapter 1 room by room, the TAS endings, the Leonardo campaign, Chapter 2, demo rooms |
| [docs/rooms.md](docs/rooms.md) | the room format and exporting rooms from the game |
| [docs/developing.md](docs/developing.md) | how the code fits together, the invariants, adding a mechanic |
| [docs/history.md](docs/history.md) | the lab notebook: what was found when, and corrections |

## Layout

```
model/          the port of Player.cs and the Monocle engine (celeste.h, celeste.c), state equality, room transition
sim/ search/    the simulator, the beam search
harness/        CBMC harnesses: one room, a window of a route, two rooms across a transition
celeste_sat/    the Python library: TAS files, rooms, builds, states, transitions, CBMC, map files, recordings
tools/          command lines: solve.py, windows.py, cross.py, chapter.py, splice_tas.py, celestetas.py, ...
tests/          checks with a pass/fail answer (tools/run_tests.sh runs them)
experiments/    the scripts behind particular findings
hpc/            Slurm scripts for cluster runs
rooms/          demo rooms; rooms/vanilla/ for rooms exported from the game
data/recordings/  recordings from the real game (CelesteTAS ExportGameInfo)
results/        routes, files to play them in the game, the replay page
```

## Credits

Madeline's movement is ported from Celeste's published `Player.cs`
([NoelFB/Celeste](https://github.com/NoelFB/Celeste), MIT) and brought up to
the current game (v1.4) from the official changelogs. Mods that patch these
methods and recordings of the game filled in the rest. The community TAS by
VampireFlower and the Celeste TAS community is the reference route. It is
downloaded at a pinned commit, not copied here. Nothing from the game itself
is in this repository. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
