# data/recordings/

Recordings from the real game: Celeste 1.4.0.0, Everest 1.6580.0, CelesteTAS
3.47.1, written by `ExportGameInfo`. Each row is one frame: the input line,
then Madeline's exact position (pixel + subpixel), speed, state, statuses
and room. They are the ground truth the model is held to:

```
python3 tests/recordings.py data/recordings      # every frame of every recording against the model
```

| file | what was played |
|---|---|
| `celeste-sat-1a_lvl_1.txt`, `celeste-sat-1a_lvl_3.txt` | the project's routes for rooms 1 and 3 (`results/celestetas/`) |
| `celeste-sat-probe-cooldown.txt` | the dash cooldown probe |
| `celeste-sat-probe-1to2.txt` | room 1, then idle through the transition into room 2 |
| `celeste-sat-probe-up-*.txt` | room 1 left seven ways (`experiments/make_up_probes.py`): the upward stop point |
| `community-lvl3-original.txt` | the community TAS's `#lvl_3` (and into `lvl_4`) |
| `community-lvl3-edit.txt` | the same with the SAT's 106-frame ending |
| `celeste-sat-community-lvl4.txt` | the community TAS from `#lvl_4` to `#lvl_5`, with the zip mover's position |
| `celeste-sat-community-lvl4-edit.txt` | `lvl_4` after the 106-frame `lvl_3` ending (dies on spikes, in the game as in the model) |
| `celeste-sat-1a-6a118.txt` | Chapter 1 from the start with the 118-frame `lvl_6a` (`results/celestetas/1a_6a118_check.tas`): matches for 880 frames, to her death in `lvl_6a`; found the tiles outside the rooms |
| `celeste-sat-2a-chase.txt` | the Chapter 2 chase (the file is rebuilt in `results/celestetas/2a_chase_recorded.tas`, which records `celeste-sat-2a-gate.txt` with the gate's position): found the dream-block bugs; open at the switch gate, `2a_lvl_6` frame 227 |
| `celeste-sat-2a-committed-route.txt` | `results/celestetas/2a_chase.tas` with the switch gate tracked (first saved as `celeste-sat-2a-gate.txt`): dies in `2a_lvl_6` before the switch, in the game as in the model |

`tests/recordings.py` knows the edit (`EDIT_*` there) and computes the entry
into `lvl_4` after it. New recordings go here, named `celeste-sat-*.txt` (or `celeste-sat-2a-*.txt`
for Chapter 2).
