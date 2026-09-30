/*
 * solve.c -- CBMC harness. Every frame's input is nondeterministic; CBMC is
 * asked to prove that Madeline can NOT leave the room within NFRAMES frames.
 * A counterexample to that claim is a speedrun; "VERIFICATION SUCCESSFUL"
 * means no input sequence of that length exists (within the model).
 * The input rules (symmetry breaking, dominance) are in input_rules.h.
 */
#define MODEL_ASSUME(c) __CPROVER_assume(c)
#ifndef NO_SYMMETRY
/* Grab is irrelevant unless a wall is close (see grab_can_matter); checked
 * inside the step, where the collision window of this frame is loaded. */
#define FRAME_HOOK(s, in) __CPROVER_assume(!(in).grab || grab_can_matter(s))
#endif
#include "celeste.c"
#include "input_rules.h"

#ifndef NFRAMES
#define NFRAMES 60
#endif

Input inputs[NFRAMES];

int main(void)
{
    State s;
#ifdef START_STATE_FILE
    /* start from a concrete mid-run state written by `sim -s K start.h` */
#include START_STATE_FILE
    s = START_STATE;
#else
    celeste_init(&s, SPAWN_X, SPAWN_Y);
#endif
    speed_bounds_from(&s);

    for (int f = 0; f < NFRAMES; f++) {
        Input in = free_input(&s);
        inputs[f] = in;
        celeste_step(&s, in);
        after_step(in, &s);
    }

    __CPROVER_assert(!s.exited, "no way out within NFRAMES frames");
    return 0;
}
