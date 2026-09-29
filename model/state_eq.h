/*
 * state_eq.h -- same_future(a, t): will state a behave exactly like state t
 * from now on, whatever the inputs? (Solver build.)
 *
 * Every field is compared except those that cannot influence anything any
 * more: lastAim and the press edges are rewritten from the input at the
 * start of every frame before anything reads them, demoDashed is only set
 * and read inside one frame, and a value that belongs to a timer is only
 * read while that timer runs (the variable jump speed, the retained wall
 * speed, the forced move direction, the wall boost direction, the dash
 * coroutine's stage and wait, and the speed before a dash until the dash
 * has read it). Some values are set on entering a state before any read:
 * lastClimbMove (every climbing frame), dashStartedOnGround (DashBegin) and
 * climbNoMoveTimer (ClimbBegin) only count in their own state. tests/fuzz.c
 * checks all this: two states that differ only in those fields stay equal
 * under random inputs.
 */
#ifndef STATE_EQ_H
#define STATE_EQ_H

static bool same_future(const State *a, const State *t)
{
#define EQ(f) (a->f == t->f)
    if (!(EQ(x) && EQ(y) && EQ(remX) && EQ(remY) && EQ(spdX) && EQ(spdY)
          && EQ(state) && EQ(facing) && EQ(ducking) && EQ(onGround) && EQ(dashes) && EQ(moveX)
          && EQ(wallSlideDir) && EQ(autoJump) && EQ(dashDirX) && EQ(dashDirY)
          && EQ(maxFall) && EQ(stamina) && EQ(hopWaitX)
          && EQ(liftSpeedX) && EQ(liftSpeedY)
          && EQ(jumpGraceTimer) && EQ(varJumpTimer) && EQ(dashCooldownTimer) && EQ(dashRefillCooldownTimer)
          && EQ(dashAttackTimer) && EQ(wallSlideTimer) && EQ(wallSpeedRetentionTimer) && EQ(forceMoveXTimer)
          && EQ(wallBoostTimer) && EQ(coActive) && EQ(freezeTimer)
          && EQ(prevJump) && EQ(prevDash) && EQ(prevCDash) && EQ(jumpBuf) && EQ(dashBuf) && EQ(cdashBuf)
          && EQ(exited) && EQ(dead)))
        return false;
#if NZIPMOVERS > 0
    for (int i = 0; i < NZIPMOVERS; i++) {
        if (a->zipTimer[i] != t->zipTimer[i]) return false;
    }
#endif
    if (t->varJumpTimer > 0 && !(EQ(varJumpSpeed) && EQ(varJumpLong))) return false;
    if (t->wallSpeedRetentionTimer > 0 && !EQ(wallSpeedRetained)) return false;
    if (t->forceMoveXTimer > 0 && !EQ(forceMoveX)) return false;
    if (t->wallBoostTimer > 0 && !EQ(wallBoostDir)) return false;
    if (t->coActive && !(EQ(coStage) && EQ(coWait))) return false;
    if (t->coActive && t->coStage <= 1 && !(EQ(beforeDashSpdX) && EQ(beforeDashSpdY))) return false;
    if (t->state == ST_DASH && !EQ(dashStartedOnGround)) return false;   /* set by DashBegin */
    if (t->state == ST_CLIMB && !EQ(climbNoMoveTimer)) return false;     /* set by ClimbBegin */
    return true;
#undef EQ
}

#endif
