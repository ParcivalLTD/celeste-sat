/*
 * cross.c -- CBMC harness across a room transition (driven by tools/cross.py).
 *
 * Room A and room B are two builds of the model in the same program
 * (a_step / b_step, see model_a.c / model_b.c written by cross.py). The run
 * starts in room A from START (a known route after K frames), plays
 * A_STEPS free frames that must end with leaving A into B on the last of
 * them, applies the room transition (model/transition.h), and then plays up
 * to B_STEPS free frames in B. The claim CBMC tries to refute: "B's state
 * never becomes TARGET". TARGET is the state the known route has in B after
 * some frames; reaching it means the rest of that route works unchanged
 * (model/state_eq.h), so a counterexample with fewer frames than the known
 * route is a faster route through the transition. Leaving B through its
 * goal also counts.
 */
#include "celeste.h"
#include "tables.h"
#include "cross_setup.h"      /* START, TARGET, A_STEPS, B_STEPS, TR_* */
#include "transition.h"
#include "state_eq.h"
#include "input_rules.h"

void a_step(State *s, Input in);
void b_step(State *s, Input in);

Input inputs[A_STEPS + B_STEPS + 1];

int main(void)
{
    State s = START;
    int f = 0;
    speed_bounds_from(&s);
    for (int i = 0; i < A_STEPS; i++, f++) {
        Input in = free_input(&s);
        inputs[f] = in;
        a_step(&s, in);
        after_step(in, &s);
        if (i + 1 < A_STEPS) __CPROVER_assume(!s.exited);   /* still in room A */
    }
    __CPROVER_assume(s.exited);                              /* left A (for B) on the last A frame */
    s = enter_room(s);

    bool hit = same_future(&s, &TARGET);                     /* B_STEPS may be 0 */
    for (int i = 0; i < B_STEPS; i++, f++) {
        Input in = free_input(&s);
        inputs[f] = in;
        b_step(&s, in);
        after_step(in, &s);
        hit = hit || s.exited || same_future(&s, &TARGET);
    }
    __CPROVER_assert(!hit, "the known route's state in room B is not reached sooner");
    return 0;
}
