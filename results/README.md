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
| `archive/` | Chapter 2 chase routes that no longer replay in the current model (see below) | -- |

**Not here yet:** the Leonardo campaign's output (window certificates, the
faster windows, crossings, the beam sweep). It belongs in `leonardo/`; see
ROADMAP.md, step 1.

## archive/

Kept for the record. Neither route replays in the current model, so don't
use them:

- `2a_chase_2531.tas` (+ `_celestetas`): the 12-room chase, 2,531 frames,
  2026-10-01. It dies in `2a_lvl_6` on frame 173 after the later model fixes.
- `2a_chase_rooms_3_to_7_celestetas.tas`: rooms 3-7, 833 frames. `2a_lvl_6`
  no longer leaves on its last frame.

Re-run `tools/chain_chapter2.py` for current Chapter 2 routes, after
ROADMAP.md step 3.
