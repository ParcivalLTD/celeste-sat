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

/* Fields a caller may leave out of the comparison (tools/windows.py leaves
 * out those that a concrete replay of the rest of a route shows cannot
 * change it: sim/live.c). same_future() compares everything. */
enum {
    SF_ONGROUND = 1 << 0, SF_WALLSLIDE = 1 << 1, SF_STAMINA = 1 << 2, SF_JUMPGRACE = 1 << 3,
    SF_VARJUMP = 1 << 4, SF_DASHCD = 1 << 5, SF_DASHREFILLCD = 1 << 6, SF_DASHATTACK = 1 << 7,
    SF_RETENTION = 1 << 8, SF_FORCEMOVE = 1 << 9, SF_WALLBOOST = 1 << 10, SF_MAXFALL = 1 << 11,
    SF_AUTOJUMP = 1 << 12, SF_MOVEX = 1 << 13, SF_FACING = 1 << 14, SF_HOPWAIT = 1 << 15,
    SF_DASHDIR = 1 << 16,
};

static bool same_future_mask(const State *a, const State *t, unsigned ign)
{
#define EQ(f) (a->f == t->f)
#define EQI(bit, f) ((ign & (bit)) || EQ(f))
    if (!(EQ(x) && EQ(y) && EQ(remX) && EQ(remY) && EQ(spdX) && EQ(spdY)
          && EQ(state) && EQI(SF_FACING, facing) && EQ(ducking) && EQI(SF_ONGROUND, onGround) && EQ(dashes)
          && EQI(SF_MOVEX, moveX)
          && EQ(wallSlideDir) && EQI(SF_AUTOJUMP, autoJump) && EQI(SF_DASHDIR, dashDirX) && EQI(SF_DASHDIR, dashDirY)
          && EQI(SF_MAXFALL, maxFall) && EQI(SF_STAMINA, stamina) && EQI(SF_HOPWAIT, hopWaitX)
          && EQ(liftSpeedX) && EQ(liftSpeedY) && EQ(liftLastX) && EQ(liftLastY) && EQ(liftGraceTimer)
          && EQI(SF_JUMPGRACE, jumpGraceTimer) && EQI(SF_VARJUMP, varJumpTimer) && EQI(SF_DASHCD, dashCooldownTimer)
          && EQI(SF_DASHREFILLCD, dashRefillCooldownTimer)
          && EQI(SF_DASHATTACK, dashAttackTimer) && EQI(SF_WALLSLIDE, wallSlideTimer)
          && EQI(SF_RETENTION, wallSpeedRetentionTimer) && EQI(SF_FORCEMOVE, forceMoveXTimer)
          && EQI(SF_WALLBOOST, wallBoostTimer) && EQ(coActive) && EQ(freezeTimer)
          && EQ(prevJump) && EQ(prevDash) && EQ(prevCDash) && EQ(jumpBuf) && EQ(dashBuf) && EQ(cdashBuf)
          && EQ(exited) && EQ(dead)))
        return false;
#if NZIPMOVERS > 0
    for (int i = 0; i < NZIPMOVERS; i++) {
        if (a->zipTimer[i] != t->zipTimer[i]) return false;
    }
    if (a->hopZip != t->hopZip || (t->hopZip && a->hopZipT != t->hopZipT)) return false;
#endif
#if NREFILLS > 0
    for (int k = 0; k < NREFILLS; k++)
        if (a->refillTimer[k] != t->refillTimer[k]) return false;
#endif
    if (!(ign & SF_VARJUMP) && t->varJumpTimer > 0 && !(EQ(varJumpSpeed) && EQ(varJumpLong))) return false;
    if (!(ign & SF_RETENTION) && t->wallSpeedRetentionTimer > 0 && !EQ(wallSpeedRetained)) return false;
    if (!(ign & SF_FORCEMOVE) && t->forceMoveXTimer > 0 && !EQ(forceMoveX)) return false;
    if (!(ign & SF_WALLBOOST) && t->wallBoostTimer > 0 && !EQ(wallBoostDir)) return false;
    if (t->coActive && !(EQ(coStage) && EQ(coWait))) return false;
    if (t->coActive && t->coStage <= 1 && !(EQ(beforeDashSpdX) && EQ(beforeDashSpdY))) return false;
    if (t->state == ST_DASH && !EQ(dashStartedOnGround)) return false;   /* set by DashBegin */
    if (t->state == ST_CLIMB && !EQ(climbNoMoveTimer)) return false;     /* set by ClimbBegin */
    return true;
#undef EQI
#undef EQ
}

static bool same_future(const State *a, const State *t) { return same_future_mask(a, t, 0); }

#endif
