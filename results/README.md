# results/

Routes worth keeping, in the project's TAS format (`celeste_sat/tas.py`;
CelesteTAS-compatible input lines), and the files that play them in the game.
Every route here was found or checked with the model at the commit it was
added in. After a model change, check that it still replays
(`tools/run_tests.sh` replays the ones it knows).

| path | what it is | in the game |
|---|---|---|
| `routes/ledge.tas` | demo room `ledge`, 18 frames; "18 is optimal given frames 1-8" (full model) | -- |
| `routes/ledge_17.tas` | `ledge` in 17 frames, found later by the beam search at rollout 10 | -- |
| `routes/hop.tas` | demo room `hop`, 21 frames | -- |
| `routes/ledge_k4.log`, `routes/hop_k8.log` | the SAT descents behind the two (first model) | -- |
| `routes/1a_lvl_1.tas` .. `1a_lvl_3.tas` | Chapter 1 rooms 1-3 from their spawns: 99, 115, 126 frames (beam + polish) | rooms 1 and 3 recorded, identical |
| `routes/probe_dash_cooldown.tas` | a probe: when can she dash again after a super cancels a dash? | recorded: 0.2 s |
| `celestetas/*.tas` | the same routes wrapped to play in Celeste Studio and record every frame (`tools/celestetas.py export`) | -- |
| `replay/replay.html` | a self-contained page that replays `ledge` and `hop` frame by frame (`tools/render.py replay/replay_spec.json`) | -- |
| `routes/2a_chase.tas` | the Chapter 2 chase, rooms 3-12, 2,531 frames, each room entered from the one before | not recorded |
| `celestetas/2a_chase.tas` | the same, to play in the game (loads 2A room 3, skips the cutscene, records every frame) | not recorded |
| `celestetas/2a_chase_rooms_3_to_7.tas` | rooms 3-7 in 833 frames (a different `lvl_5` and `lvl_7`) | not recorded |

`leonardo/` holds the Leonardo campaign's output: window certificates,
crossings, the beam sweep, logs and provenance (its own README;
`python3 hpc/summary.py` reads it). What it shows is in
[docs/results.md](../docs/results.md#the-leonardo-campaign-october-2026).
