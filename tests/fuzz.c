/* fuzz.c -- random input sequences through the model; prints the exact state
 * every frame (floats as hex) so two builds can be diffed. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MODEL_ASSUME(c) assert(c)
#include "../model/celeste.c"
#include "../model/state_eq.h"

static unsigned long long rng;
static unsigned rnd(void) { rng = rng * 6364136223846793005ULL + 1442695040888963407ULL; return (unsigned)(rng >> 33); }

#ifndef REFERENCE
/* The CBMC harness forbids inputs that cannot change anything (symmetry
 * breaking). Check that claim on every fuzzed frame: stepping with the
 * forbidden variant must give exactly the same state. The dominance rules
 * (presses that only fill a buffer) are checked in their narrower form:
 * such a press changes nothing but the buffer and the press flags. */
static long symChecks, symFail;
enum { IGNORE_JUMPBUF = 1, IGNORE_DASHBUF = 2 };
static void same_after(const State *s, Input a, Input b, const char *rule, int ignore)
{
    State x, y;
    memcpy(&x, s, sizeof x); memcpy(&y, s, sizeof y);
    celeste_step(&x, a);
    celeste_step(&y, b);
    /* fields rewritten from the input at the start of every frame before
     * anything reads them (lastAim, press edges) carry nothing forward */
    x.aimX = y.aimX = 0; x.aimY = y.aimY = 0;
    x.jumpEdge = y.jumpEdge = false; x.dashEdge = y.dashEdge = false; x.cdashEdge = y.cdashEdge = false;
    if (ignore & IGNORE_JUMPBUF) { x.jumpBuf = y.jumpBuf = 0; }
    if (ignore & IGNORE_DASHBUF) {
        x.dashBuf = y.dashBuf = 0; x.cdashBuf = y.cdashBuf = 0;
        x.prevDash = y.prevDash = false; x.prevCDash = y.prevCDash = false;
    }
    symChecks++;
    if (memcmp(&x, &y, sizeof x)) {
        if (symFail++ < 10) fprintf(stderr, "symmetry rule broken: %s (x=%d y=%d state=%d)\n", rule, s->x, s->y, s->state);
    }
}
static void check_symmetry(const State *s, Input in)
{
    if (s->exited || s->dead) return;
    Input v = in;
    bool frozen = TPOS(s->freezeTimer);
    if (in.jump == BTN_REPRESS && !s->prevJump) {
        v = in; v.jump = 1;
        same_after(s, in, v, "second-key press after a release = press", 0);
    }
    if (in.jump == BTN_REPRESS && s->prevJump) {        /* a press again that does not jump: only the buffer differs */
        State t; memcpy(&t, s, sizeof t);
        celeste_step(&t, in);
        if (TPOS(t.jumpBuf)) {
            v = in; v.jump = 1;
            same_after(s, in, v, "press again without a jump only fills the buffer", IGNORE_JUMPBUF);
        }
    }
    if (in.dash || in.cdash) {                          /* dash buttons that start no dash: only buffers differ */
        State t; memcpy(&t, s, sizeof t);
        celeste_step(&t, in);
        bool had = t.dashEdge || t.cdashEdge || TPOS(s->dashBuf) || TPOS(s->cdashBuf);
        bool consumed = had && !TPOS(t.dashBuf) && !TPOS(t.cdashBuf);   /* StartDash ran */
        if (!consumed) {
            v = in; v.dash = 0; v.cdash = 0;
            same_after(s, in, v, "dash buttons that start no dash only fill a buffer", IGNORE_DASHBUF);
        }
    }
    if (frozen) {                                     /* directions and grab ignored while frozen */
        v = in; v.mx = 0; v.my = 0; v.grab = false;
        same_after(s, in, v, "freeze: directions/grab", 0);
        return;
    }
    if (in.my == -1 && !(s->state == ST_DASH && s->coStage == 1) && s->state != ST_CLIMB) {
        v = in; v.my = 0;
        same_after(s, in, v, "up only matters when climbing or on the dash-direction frame", 0);
    }
    if (in.grab) {                                    /* FRAME_HOOK: this frame's window and buttons */
        State t;
        memcpy(&t, s, sizeof t);
        buttons_update(&t, in);
        load_window(&t);
        if (!grab_can_matter(&t)) {
            v = in; v.grab = false;
            same_after(s, in, v, "grab ignored away from walls", 0);
        }
    }
}
#endif

#ifndef REFERENCE
/* same_future (model/state_eq.h) ignores some fields. Check that they really
 * cannot matter: scramble exactly those in a copy of the state, then step
 * both with the same random inputs; same_future must keep holding. */
static unsigned long long rng2 = 12345;
static unsigned rnd2(void) { rng2 = rng2 * 6364136223846793005ULL + 1442695040888963407ULL; return (unsigned)(rng2 >> 33); }
static long eqChecks, eqFail;
static void scramble(State *s)
{
    s->aimX = (int)(rnd2() % 3) - 1; s->aimY = (int)(rnd2() % 3) - 1;
    s->jumpEdge = rnd2() & 1; s->dashEdge = rnd2() & 1; s->cdashEdge = rnd2() & 1;
    s->lastClimbMove = (int)(rnd2() % 3) - 1;
    s->demoDashed = rnd2() & 1;
    if (!TPOS(s->varJumpTimer)) { s->varJumpSpeed = -(float)(rnd2() % 300); s->varJumpLong = rnd2() & 1; }
    if (!TPOS(s->wallSpeedRetentionTimer)) s->wallSpeedRetained = (float)((int)(rnd2() % 600) - 300);
    if (!TPOS(s->forceMoveXTimer)) s->forceMoveX = (int)(rnd2() % 3) - 1;
    if (!TPOS(s->wallBoostTimer)) s->wallBoostDir = (rnd2() & 1) ? 1 : -1;
    if (!s->coActive) { s->coStage = (int)(rnd2() % 3); s->coWait = (int)(rnd2() % 10); }
    if (!(s->coActive && s->coStage <= 1)) {
        s->beforeDashSpdX = (float)((int)(rnd2() % 600) - 300); s->beforeDashSpdY = (float)((int)(rnd2() % 600) - 300);
    }
    if (s->state != ST_DASH) s->dashStartedOnGround = rnd2() & 1;
    if (s->state != ST_CLIMB) s->climbNoMoveTimer = (int)(rnd2() % 7);
}
static void check_same_future(const State *s)
{
    State a = *s, b = *s;
    scramble(&b);
    Input in = {0};
    for (int f = 0; f < 40 && !a.exited && !a.dead; f++) {
        if (rnd2() % 3 == 0) {
            in.mx = (signed char)((int)(rnd2() % 3) - 1); in.my = (signed char)((int)(rnd2() % 3) - 1);
            in.jump = rnd2() % 3 == 0 ? (rnd2() % 4 ? 1 : BTN_REPRESS) : 0;
            in.dash = rnd2() % 6 == 0; in.cdash = rnd2() % 15 == 0; in.grab = rnd2() % 3 == 0;
        }
        celeste_step(&a, in);
        celeste_step(&b, in);
        eqChecks++;
        if (!same_future(&b, &a)) {
            if (eqFail++ < 10) fprintf(stderr, "same_future broken after %d frames (x=%d y=%d state=%d)\n", f + 1, a.x, a.y, a.state);
            return;
        }
    }
}
#endif

int main(int argc, char **argv)
{
    rng = strtoull(argv[1], 0, 10);
    int runs = atoi(argv[2]), frames = atoi(argv[3]);
    int bias = EXITS[0][0] == EXIT_SIDE_LEFT ? -1 : 1;    /* lean towards the first exit */
    for (int r = 0; r < runs; r++) {
        State s;
        celeste_init(&s, SPAWN_X, SPAWN_Y);
        Input in = {0};
        int hold = 0;
        for (int f = 0; f < frames; f++) {
            if (hold-- <= 0) {
                hold = rnd() % 12;
                in.mx = (signed char)((int)(rnd() % 5) - 1); if (in.mx > 1) in.mx = 1;
                in.mx = (signed char)(in.mx * bias);
                in.my = (signed char)((int)(rnd() % 3) - 1);
                in.jump = rnd() % 3 == 0;
                in.dash = rnd() % 6 == 0;
                in.cdash = rnd() % 12 == 0;
                in.grab = rnd() % 3 == 0;
            } else if (rnd() % 4 == 0) {   /* occasional single-frame changes */
                in.jump = rnd() % 2; in.dash = rnd() % 5 == 0; in.cdash = rnd() % 10 == 0;
                if (rnd() % 3 == 0) in.my = (signed char)((int)(rnd() % 3) - 1);
            } else {                       /* the button stays held; sometimes pressed again with the second key */
                if (in.jump && rnd() % 5 == 0) in.jump = BTN_REPRESS;
                else if (in.jump) in.jump = 1;
                if (in.dash && rnd() % 5 == 0) in.dash = BTN_REPRESS;
                else if (in.dash) in.dash = 1;
                if (in.cdash && rnd() % 5 == 0) in.cdash = BTN_REPRESS;
                else if (in.cdash) in.cdash = 1;
            }
#ifndef REFERENCE
            check_symmetry(&s, in);
            if (f % 17 == 5) check_same_future(&s);
#endif
            celeste_step(&s, in);
            printf("%d %d %d %a %a %a %a %d %d %d %d %d %d %a %d %a %a %a %a %d %d\n", r, s.x, s.y, s.remX, s.remY,
                   s.spdX, s.spdY, s.state, s.ducking, s.onGround, s.dashes, s.exited, s.dead, s.stamina, s.hopWaitX,
                   s.liftSpeedX, s.liftSpeedY, s.liftLastX, s.liftLastY, s.zipTimer[0], s.zipTimer[1]);
            if (s.exited || s.dead) break;
        }
    }
#ifdef COVERAGE
    for (int k = 0; k < C_NCOV; k++) fprintf(stderr, "%s\t%ld\n", COV_NAMES[k], COVC[k]);
#endif
#ifndef REFERENCE
    fprintf(stderr, "symmetry checks: %ld, broken: %ld\n", symChecks, symFail);
    fprintf(stderr, "same_future checks: %ld, broken: %ld\n", eqChecks, eqFail);
    if (symFail || eqFail) return 3;
#endif
    return 0;
}
