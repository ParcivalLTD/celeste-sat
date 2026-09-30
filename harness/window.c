/*
 * window.c -- CBMC harness for a window inside a known route (driven by
 * tools/windows.py).
 *
 * The run starts from the route's exact state after K frames (START_STATE)
 * and plays up to W free frames. The claim CBMC tries to refute: "she never
 * reaches TARGET_STATE", the route's state after K + W + 1 frames (or the
 * room's exit). Reaching it (model/state_eq.h: every field that can still
 * matter is equal) within W frames means the rest of the route works
 * unchanged one frame sooner, so a counterexample is a faster route through
 * the window, and "VERIFICATION SUCCESSFUL" proves that no input sequence
 * gets from the route's state at frame K to its state at frame K + W + 1 in
 * fewer frames.
 *
 * SF_IGNORE (a mask, model/state_eq.h) leaves fields out of the comparison
 * that a concrete replay of the rest of the route shows cannot change it
 * (sim/live.c); a route found that way is replayed before it counts.
 *
 * The input rules are those of solve.c, except that the dominance rules
 * (presses that only fill a buffer) are off for the last 5 frames: there a
 * press can leave a buffer that the target state has.
 */
#define MODEL_ASSUME(c) __CPROVER_assume(c)
#ifndef NO_SYMMETRY
#define FRAME_HOOK(s, in) __CPROVER_assume(!(in).grab || grab_can_matter(s))
#endif
#include "celeste.c"
#include "state_eq.h"
#include "input_rules.h"
#include START_STATE_FILE          /* START_STATE: the route after K frames */
#include TARGET_STATE_FILE         /* TARGET_STATE: the route after K + W + 1 frames */

#ifndef W
#define W 8
#endif
#ifndef SF_IGNORE
#define SF_IGNORE 0u
#endif

Input inputs[W];

int main(void)
{
    State s = START_STATE;
    bool hit = false;
    speed_bounds_from(&s);
    for (int f = 0; f < W; f++) {
        rules_dominance = f < W - 5;
        Input in = free_input(&s);
        inputs[f] = in;
        celeste_step(&s, in);
        after_step(in, &s);
        hit = hit || s.exited || same_future_mask(&s, &TARGET_STATE, SF_IGNORE);
    }
    __CPROVER_assert(!hit, "the route's state after K + W + 1 frames is not reached within W frames");
    return 0;
}
