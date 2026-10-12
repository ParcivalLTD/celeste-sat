# experiments/

The scripts behind specific findings in [docs/results.md](../docs/results.md).
Unlike `tests/`, they don't answer pass/fail. Most need CBMC and minutes to
hours, and most start from what `tests/chain_tas.py` leaves in
`build/chain_tas/`, so run that first.

| script | question | finding |
|---|---|---|
| `tas_endings.py` | can each room of the community TAS be left a frame sooner, with its last 10 frames free? | 6 of 19 rooms: yes, but each faster ending breaks the next room's inputs |
| `tas_crossings.py` | can she be in the TAS's state a few frames into the next room one frame sooner? (`tools/cross.py` at every room change) | `lvl_1`→`lvl_2`, `lvl_2`→`lvl_3`, `lvl_3`→`lvl_4`: no |
| `next_room.py` | after a different ending of a room, do the TAS's inputs for the next room still work? | -- |
| `make_up_probes.py` | writes CelesteTAS files that leave room 1 in seven ways, to record where an upward transition stops her | 9 px above the bottom in 184 px rooms |
| `chain_3b_5.py`, `scan_entry.c` | which entries into `lvl_3b` reproduce the TAS's exit (from before `lvl_4` matched the game)? | historical |
