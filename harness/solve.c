/*
 * solve.c -- CBMC harness. Every frame's input is nondeterministic; CBMC is
 * asked to prove that Madeline can NOT leave the room within NFRAMES frames.
 * A counterexample to that claim is a speedrun; "VERIFICATION SUCCESSFUL"
 * means no input sequence of that length exists (within the model).
 */
#define MODEL_ASSUME(c) __CPROVER_assume(c)
#include "celeste.c"

#ifndef NFRAMES
#define NFRAMES 60
#endif

Input inputs[NFRAMES];

signed char nondet_schar(void);
_Bool nondet_bool(void);

int main(void)
{
    State s;
#ifdef START_STATE_FILE
    /* start from a concrete mid-run state written by `sim -s K start.h` */
#include START_STATE_FILE
    s = START_STATE;
    load_window(&s); /* (the window is reloaded every frame anyway) */
#else
    celeste_init(&s, SPAWN_X, SPAWN_Y);
#endif

    for (int f = 0; f < NFRAMES; f++) {
        Input in;
        in.mx = nondet_schar();
        in.my = nondet_schar();
        __CPROVER_assume(in.mx >= -1 && in.mx <= 1);
        __CPROVER_assume(in.my >= -1 && in.my <= 1);
        in.jump = nondet_bool();
        in.dash = nondet_bool();

#ifndef NO_SYMMETRY
        /* Symmetry breaking (sound: these inputs cannot change anything).
         *  - Directions are ignored during freeze frames (only buttons are
         *    buffered) and after leaving the room.
         *  - "Up" only matters for the dash direction, which is read on the
         *    frame the dash coroutine runs its body. */
        bool frozen = TPOS(s.freezeTimer);
        if (frozen || s.exited) { __CPROVER_assume(in.mx == 0 && in.my == 0); }
        if (s.exited) { __CPROVER_assume(!in.jump && !in.dash); }
        if (!(s.state == ST_DASH && s.coStage == 1)) { __CPROVER_assume(in.my != -1); }
        /*  - Keeping Dash held once its 5-frame buffer is used up or consumed
         *    does nothing except block the next press, so releasing instead
         *    is never worse. */
        if (in.dash && s.prevDash) { __CPROVER_assume(s.dashBuf >= 2); }
#endif
#ifdef NODASH
        __CPROVER_assume(!in.dash);
#endif
#ifdef NOJUMP
        __CPROVER_assume(!in.jump);
#endif
        inputs[f] = in;

        celeste_step(&s, in);
        __CPROVER_assume(!s.dead);

#ifndef NO_INVARIANTS
        /* Redundant facts that always hold (the simulator checks them); they
         * give the SAT solver bounds it would otherwise have to rediscover. */
        __CPROVER_assume(s.remX >= -0.5f && s.remX <= 0.5f);
        __CPROVER_assume(s.remY >= -0.5f && s.remY <= 0.5f);
        __CPROVER_assume(s.spdX >= -400.0f && s.spdX <= 400.0f);
        __CPROVER_assume(s.spdY >= -250.0f && s.spdY <= 250.0f);
#endif
    }

    __CPROVER_assert(!s.exited, "no way out within NFRAMES frames");
    return 0;
}
