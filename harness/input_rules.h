/*
 * input_rules.h -- one frame of free input for CBMC, with the rules that keep
 * the formula small without losing any route (shared by solve.c and
 * cross.c).
 *
 * Symmetry breaking (these inputs cannot change anything):
 *  - Directions and Grab are ignored during freeze frames (only the buttons
 *    are buffered) and after leaving the room.
 *  - "Up" only matters while climbing and for the dash direction, which is
 *    read on the frame the dash coroutine runs its body.
 *  - Pressing a held button again (the second key) is the same as holding
 *    it unless it was held on the previous frame.
 *  - Grab away from walls: FRAME_HOOK in the model build (grab_can_matter).
 * Dominance (a route that breaks these can be rewritten into one that keeps
 * them and leaves the room on the same frame): with two keys per button a
 * press is possible on any frame, so a press that only fills the 5-frame
 * buffer can be replaced by a press on the frame the buffer would be used.
 * Holding Dash or Crouch Dash does nothing but keep a buffer. So Dash and
 * Crouch Dash are only pressed, and only on a frame where the press starts
 * a dash; one of them at a time (both = a crouch dash); Jump is pressed again
 * while held only on a frame where that press jumps (checked after the step:
 * the buffer is consumed exactly when it is used).
 * tests/fuzz.c checks all of these on random states.
 */
#ifndef INPUT_RULES_H
#define INPUT_RULES_H

signed char nondet_schar(void);
unsigned char nondet_uchar(void);
_Bool nondet_bool(void);

#ifndef TPOS
#define TPOS(t) ((t) > 0)
#endif

/* Speed bounds for the invariants in after_step (tests/fuzz.c checks them).
 * Lift boosts from moving solids go well past the usual ones: a hyper off a
 * zip mover is (260 + 250) * 1.25 px/s, and a dash keeps a faster speed.
 * ANY_ZIPMOVERS: set by tools/cross.py when either room has one. */
#if (defined(NZIPMOVERS) && NZIPMOVERS > 0) || defined(ANY_ZIPMOVERS)
#define MAX_SPEED_X 1000.0f
#define MAX_SPEED_Y 400.0f
#else
#define MAX_SPEED_X 400.0f
#define MAX_SPEED_Y 250.0f
#endif

/* The dominance rules can be switched off for some frames (harness/window.c:
 * a press near the end of a window may leave a buffer the target state has). */
static bool rules_dominance = true;

static Input free_input(const State *s)
{
    Input in;
    in.mx = nondet_schar();
    in.my = nondet_schar();
    __CPROVER_assume(in.mx >= -1 && in.mx <= 1);
    __CPROVER_assume(in.my >= -1 && in.my <= 1);
    in.jump = nondet_uchar();
    in.dash = nondet_uchar();
    in.cdash = nondet_uchar();
    __CPROVER_assume(in.jump <= BTN_REPRESS && in.dash <= BTN_REPRESS && in.cdash <= BTN_REPRESS);
    in.grab = nondet_bool();
#ifndef NO_SYMMETRY
    bool frozen = TPOS(s->freezeTimer);
    if (frozen || s->exited) { __CPROVER_assume(in.mx == 0 && in.my == 0 && !in.grab); }
    if (s->exited) { __CPROVER_assume(!in.jump && !in.dash && !in.cdash); }
    if (!(s->state == ST_DASH && s->coStage == 1) && s->state != ST_CLIMB) { __CPROVER_assume(in.my != -1); }
    __CPROVER_assume(in.jump != BTN_REPRESS || s->prevJump);
    __CPROVER_assume(in.dash != BTN_REPRESS || s->prevDash);
    __CPROVER_assume(in.cdash != BTN_REPRESS || s->prevCDash);
    if (rules_dominance) {
        __CPROVER_assume(in.dash == 0 || in.dash == (s->prevDash ? BTN_REPRESS : 1));
        __CPROVER_assume(in.cdash == 0 || in.cdash == (s->prevCDash ? BTN_REPRESS : 1));
        __CPROVER_assume(!(in.dash && in.cdash));
    }
#endif
#ifdef NODASH
    __CPROVER_assume(!in.dash && !in.cdash);
#endif
#ifdef NOJUMP
    __CPROVER_assume(!in.jump);
#endif
#ifdef NOGRAB
    __CPROVER_assume(!in.grab);
#endif
    return in;
}

/* after the step: she is alive, and the dominance rules above */
static void after_step(Input in, const State *s)
{
    __CPROVER_assume(!s->dead);
#ifndef NO_SYMMETRY
    if (rules_dominance) {
        __CPROVER_assume(in.jump != BTN_REPRESS || !TPOS(s->jumpBuf));
        __CPROVER_assume(!in.dash || !TPOS(s->dashBuf));
        __CPROVER_assume(!in.cdash || !TPOS(s->cdashBuf));
    }
#endif
#ifndef NO_INVARIANTS
    /* Redundant facts that always hold (the simulator checks them); they
     * give the SAT solver bounds it would otherwise have to rediscover. */
    __CPROVER_assume(s->remX >= -0.5f && s->remX <= 0.5f);
    __CPROVER_assume(s->remY >= -0.5f && s->remY <= 0.5f);
    __CPROVER_assume(s->spdX >= -MAX_SPEED_X && s->spdX <= MAX_SPEED_X);
    __CPROVER_assume(s->spdY >= -MAX_SPEED_Y && s->spdY <= MAX_SPEED_Y);
#endif
}

#endif
