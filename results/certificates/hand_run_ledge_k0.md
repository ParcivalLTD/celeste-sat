# One window, step by step: `ledge`, K = 0, W = 8

Step 2 of the certificate plan, run step by step, command by command. Machine and tools: [versions.txt](versions.txt) (CBMC 5.95.1,
CaDiCaL 1.7.3, drat-trim built from source, 4 cores).

The question: can any 8 inputs take Madeline from the `ledge` route's
state after 0 frames (the spawn) to a state that matches its state after 9
frames, on the compared fields, within the model? UNSAT means that no input
sequence does: frames 1 to 9 of `results/routes/ledge.tas` cannot be done in 8
and end in the same state.

```bash
# 1. the window's headers and mask (and CBMC's own verdict)
python3 tools/windows.py rooms/ledge.txt results/routes/ledge.tas --width 8 --from 0 --to 0 --jobs 1 --out build/hand_ledge
#    -> frames 1..9 in 8: no (361s); fields left out: onGround jumpGraceTimer dashRefillCooldown dashAttack moveX facing
#       (SF_IGNORE = 24777)

# 2. the same CBMC command as windows.py's query(), without --trace --json-ui, writing DIMACS
cd build/hand_ledge
cbmc ../../harness/window.c -I . -I ../../model -I ../../harness -DW=8 \
     '-DSTART_STATE_FILE="win_0_start.h"' '-DTARGET_STATE_FILE="win_0_target.h"' -DSF_IGNORE=24777u \
     --dimacs --outfile win_0.cnf
#    -> 13 s; p cnf 3628991 11105266 (290 MB; CBMC's variable names follow as comment lines at the end)

# 3. CaDiCaL, writing a binary DRAT proof
cadical -q win_0.cnf win_0.drat
#    -> s UNSATISFIABLE, exit code 20, 9 min 10 s, proof 1,107,123,812 bytes

# 4. drat-trim
drat-trim win_0.cnf win_0.drat -t 20000
#    -> s VERIFIED, 19 min 32 s (verification 1,172 s)
#       865,606 of 11,105,266 clauses and 1,282,741 of 20,285,113 lemmas in the core, 0 RAT lemmas
```

CNF SHA-256 begins `767c7385b1d4e1b6`. CBMC's own solver took 6 min (the
default MiniSat, with its preprocessing). CaDiCaL took 9 min, and checking took
about twice as long as solving.

drat-trim printed 9 warnings, "backward mode ignores deletion of (pseudo)
unit clause". That is standard. It keeps unit clauses the proof deletes, and
every kept clause follows from the formula anyway, so the check stays sound.

The pipeline's negative checks (a known yes comes back SAT, a truncated
proof is rejected) are `python3 tools/certify.py --self-check`, step 3 of the plan.
