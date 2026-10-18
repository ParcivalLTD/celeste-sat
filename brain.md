# brain.md -- the working state

Read this first when you pick the project up again, human or AI. It is the
short version of where things are, what to do next and how, and the traps
that already cost days. The long-form plan is [ROADMAP.md](ROADMAP.md), what
happened when is [docs/history.md](docs/history.md), and the measurements are
[docs/results.md](docs/results.md). Update this file at the end of every
working session: the state, the next step, anything you learnt the hard way.

Last updated: 2026-10-18.

## The state in ten lines

- **The model matches the game, everywhere it has been checked.**
  `python3 tests/recordings.py data/recordings` reports MATCH for all 19
  recordings. Chapter 1: 16 recordings, the longest 880 frames over 8 rooms
  to a death on the same frame. Chapter 2: 3 recordings, the longest 851
  frames over 5 rooms to a death, the switch gate's position included. The
  community 1A TAS replays exactly (2,275 frames of control, 19 rooms).
- **The certificate holds** (Leonardo, Oct 2026): no 12- or 16-frame window
  of the community 1A TAS can be shortened to the same state, and the same
  holds across all 18 room transitions (3,826 windows proven, 6 timeouts).
  It was computed before the model had the tiles outside the rooms, so 86
  frames near room edges need re-checking (step 3 below).
- **Nothing is faster than the community TAS yet.** The record is
  **0:49.079** (2,887 frames, VampireFlower/CelesteTAS `1A.tas`). The
  118-frame `lvl_6a` lead is void: the game has wall above the room. The
  "faster" Leonardo windows are faster room *endings* in another exit state,
  and the next room's inputs fail after each.
- **Chapter 2 routes are all void.** They were made with model bugs, fixed
  since. They must be solved again (step 2 below).
- **No compute cluster.** The Leonardo account expired on 2026-10-12. Long
  searches run on the PC.
- Open PR: **#8** (the touch switch fix and this file). Merge it on GitHub.

## Setting up the Windows PC

The tools are Linux programs (gcc, Python 3, CBMC). On Windows use WSL2:

```powershell
wsl --install -d Ubuntu          # once, in an admin PowerShell; reboot if asked
```

Then, in the Ubuntu shell:

```bash
sudo apt update && sudo apt install -y gcc python3 cbmc git
cd /mnt/r/celeste-sat            # the R:\celeste-sat folder
# if /mnt/r does not exist (R: is a network or virtual drive):
#   sudo mkdir -p /mnt/r && sudo mount -t drvfs R: /mnt/r
nproc                            # cores: the beam search uses all of them
bash tools/run_tests.sh --quick  # must end "all checks passed"
```

`.gitattributes` keeps every file's line endings LF, on Windows too: bash
scripts with Windows (CRLF) endings fail in WSL. Builds on `/mnt/r` work but are slower than inside WSL's own filesystem. If
the long searches feel slow, clone a second copy to `~/celeste-sat` in WSL
for compute and copy results back.

The game's map files go into `game/` (never into git): `game/1-ForsakenCity.bin`
is there; copy `2-OldSite.bin` from `<Celeste>\Content\Maps` too.
`CELESTE_DIR` can point at the Celeste install instead
(`export CELESTE_DIR=/mnt/c/Program\ Files\ \(x86\)/Steam/steamapps/common/Celeste`).

Then the full check against the game data:

```bash
python3 tests/chain_tas.py                     # "2275 frames of the community TAS played exactly"
python3 tests/recordings.py data/recordings    # "MATCH"
bash tools/run_tests.sh --vanilla --sat        # everything; takes a while
```

## Next steps, in order

### 1. Merge PR #8 and `git pull`

The touch switch fix and this file. Afterwards `git status` should be clean,
apart from leftovers listed in "Cleanup on the PC" below.

### 2. Solve the Chapter 2 chase again (hours; on the PC)

Every Chapter 2 route was made with at least one of the four bugs the
recordings found. With the model now matching the game:

```bash
python3 tools/chain_chapter2.py --polish        # 12 rooms, each from the previous exit; hours
python3 tools/celestetas.py chain build/chapter2_chase/2A_chase.tas \
    --load "2 3" --skip-cutscene --dump celeste-sat-2a-chase-v2.txt \
    -o results/celestetas/2a_chase.tas
```

It reuses a room's result only if it was solved from the same start state,
so it can be stopped and restarted. Then **play
`results/celestetas/2a_chase.tas` in Celeste Studio**. Put the recording
(`celeste-sat-2a-chase-v2.txt` in the Celeste folder) into `data/recordings/`
and check it: `python3 tests/recordings.py data/recordings`. Commit the
route (`build/chapter2_chase/2A_chase.tas` -> `results/routes/2a_chase.tas`)
with the per-room frame counts in `docs/results.md`. The community TAS's
chase (rooms 4-12) is 2,221 frames; the old, buggy search got 2,429.

Then turn on the run_tests step again: it is skipped until the route is
re-solved (`CHASE_ROUTE_FIXED=1 bash tools/run_tests.sh`, then remove the
skip in `tools/run_tests.sh`).

### 3. Re-check the Chapter 1 certificate near room edges (an evening)

The Leonardo windows were proven before the model had the map's tiles
around each room (`; outside`). New walls can only add options (a wall jump
off an extended wall, say), so a proof might not survive. Only 86 of the
2,275 frames come within reach of a room edge, mostly the last frames
before a transition and 22 in `lvl_6b`. Re-run the windows that cover those
frames with `tools/windows.py`, at W = 12 (`hpc/make_tasks.py` shows how a
room is cut into windows). If all are still "no", the certificate stands
for the current model. Say so in `docs/results.md`.

### 4. The faster endings (the record attempt; weeks)

The only frames left in Chapter 1 are in the seams between rooms. The
candidates: `lvl_6a` −5, `lvl_12` −4, `lvl_9b` −3, `lvl_3b` −2 (faster room
endings, each in a different exit state). For each, the next room must be
done from the new entry within its TAS frames plus the saving minus one:

```bash
python3 tools/solve.py rooms/vanilla/1a_lvl_7.txt --start <entry.h> \
    --tas build/chain_tas/lvl_7/route.tas --polish --no-sat --beam-width 500000
python3 tools/cross.py ...      # SAT across the seam: see docs/methods.md
python3 tools/splice_tas.py chapter --room lvl_6a=<route.tas> -o build/1a_try.tas
python3 tests/chain_tas.py --tas build/1a_try.tas
```

`hpc/candidate_checks.sbatch` is the cluster version; its entry states are
in `hpc/entry_states/` (the `6b_after_6a_118` one is void). Rerun the beam
sweep over Chapter 1 first: the rooms changed (outside tiles), so its old
results are stale. A per-room loop for the PC:

```bash
for room in lvl_1 lvl_2 lvl_3 lvl_4 lvl_3b lvl_5 lvl_6 lvl_6a lvl_6b lvl_6c lvl_7 \
            lvl_8 lvl_8b lvl_9 lvl_9b lvl_10a lvl_11 lvl_12 lvl_12a; do
  start=build/chain_tas/entry_${room}.h; s=(); [ -f $start ] && s=(--start $start)
  python3 tools/solve.py rooms/vanilla/1a_${room}.txt "${s[@]}" \
      --tas build/chain_tas/${room}/route.tas --polish --no-sat \
      --beam-width 100000 --out build/sweep/${room} | tail -2
done
```

Anything faster is a candidate, not a result: check the next room, then the
whole chapter, then play it in the game.

### 5. The community 2A TAS through the model (a day)

The cheapest strong check of Chapter 2, the same one that made Chapter 1
believable. The first try failed in `2a_lvl_4`, before the dream-block
fixes. Generalise `tests/chain_tas.py` to a chapter argument (ROADMAP step
3.2 has the details: the chase starts in `lvl_3` after the cutscene skip,
the chaser history runs on across rooms). Every room's inputs must leave it
on their last frame.

### 6. The paper (start now, in parallel)

ROADMAP step 4 has the outline and what may and may not be claimed. The
story is stronger than it was a week ago: the recordings found seven model
bugs (falling-unduck, the upward stop point, the climb trigger, three
dream-dash ones, the touch switch) plus the tiles outside rooms, each one
pinned to a frame. That list is the fidelity section, and it shows the
checks have teeth.

### 7. Before pointing people at the repository

- Licence: done (MIT, 2026-10-13).
- The git history still has game content and decompiled game code
  (`1-ForsakenCity.bin`, `LevelLoader.cs`, `Switch.cs`, `SwitchGate.cs`, an
  Everest log). ROADMAP step 5 has the `git filter-repo` line. It rewrites
  every commit, so do it once, deliberately, before anyone forks.

## How to play a route in the game and check it

1. Open the `.tas` file from `results/celestetas/` in Celeste Studio and play
   it. The file's `ExportGameInfo, <name>.txt` line writes the recording into
   the Celeste folder. Studio may re-align the numbers when it saves; that
   changes nothing.
2. Copy the recording into `data/recordings/` (the name must start with
   `celeste-sat-`) and run `python3 tests/recordings.py data/recordings`.
3. The first frame that differs is a model bug or a wrong assumption. Find
   it in the game's code: ILSpy on `Celeste.dll`
   (`~/.dotnet/tools/ilspycmd -t Celeste.<Type> Celeste.dll`), or the
   published `Player.cs`. Never commit decompiled code (`.gitignore` blocks
   `*.cs`).
4. Fix the model, then `sh tests/diff.sh 40 300 400` (both builds identical,
   the new coverage counter non-zero), the recordings, the community TAS,
   `bash tools/run_tests.sh --quick --sat`.

To record an entity's position too: `ExportGameInfo, <file>.txt, SwitchGate`
(or `ZipMover`, ...). It appears in the Entities column.

## Lessons that cost time (read before changing the model)

- **Read the whole signature.** `new PlayerCollider(OnPlayer, null, new
  Hitbox(30f, 30f, -15f, -15f))`: the box present is the *feather* collider;
  the touch box is the null argument (the entity's 16 × 16 Collider). That
  misreading reverted a correct fix and cost a day. When ILSpy shows a call,
  look up which parameter each argument fills.
- **The game decides, not the search.** A model change made because the
  search was stuck is suspect. A change made because a recording differs on
  a named frame is how the model got right.
- **The published `Player.cs` is older than 1.4.** The dream-block exit push
  is in the game, not in that source (CommunalHelper's copy of the 1.4 code
  showed it). When the published code and a recording disagree, believe the
  recording and look for newer code.
- **Outside a room is not air.** Celeste extends edge tiles 3 tiles out
  (`celeste_map.solid_grid`). Any route that leaves the room's grid must be
  checked against the exported `; outside` tiles.
- **One frame of order matters.** Entities update by `Depth`, and equal
  depths update in the order their depth was last set. `DreamDashEnd` resets
  Madeline's depth, so the update order can change mid-room. Not modelled; no
  recording has needed it yet, but it is the first suspect for a one-frame
  difference with a depth-0 entity.
- **Recording quirks.** CelesteTAS adds columns (`LiftBoost(...)`) before
  the room column; `Frozen(n)` rows after a transition are frames the game
  does not update; frames are missing while she is dead. `parse_dump` and
  `recordings.py` handle these now. Two `ExportGameInfo` lines with the same
  file name overwrite each other's recordings.
- **Every model change voids routes and proofs.** Note the commit every
  result was computed at, and replay the saved routes after a change.

## Cleanup on the PC (2026-10-18)

This folder was updated from commit 588c008 to the PR #8 branch without a
shell, so files the update deleted are still on disk as untracked
leftovers. They are safe to delete; `git status` lists them. In WSL:
`git clean -n` shows what would go, `git clean -f -d` removes it (it keeps
`game/` and `build/`, which are ignored). The old `1-ForsakenCity.bin` in the
root is ignored too; the tools read `game/1-ForsakenCity.bin`.
