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
 * climbNoMoveTimer (ClimbBegin) only count in their own state, as do the dream
 * dash's two (dreamDashCanEndTimer and dreamJump, both set by
 * dream_dash_begin). Of the chaser history only the entries still inside the
 * longest chase delay (CHASER_MAX_DELAY in model/celeste.c) can be read again.
 * tests/fuzz.c checks all this: two states that differ only in those fields
 * stay equal under random inputs.
 */
#ifndef STATE_EQ_H
#define STATE_EQ_H

/* model/celeste.c defines this (and checks it against CHASER_HIST_LEN), but
 * harness/cross.c includes celeste.h rather than celeste.c and gets the room's
 * chaser counts from cross_setup.h instead, so define it here if it is missing. */
#if defined(HAS_CHASER) && HAS_CHASER && !defined(CHASER_MAX_DELAY)
#define CHASER_MAX_DELAY (CHASER_DELAY + 24 * (NCHASERS - 1))
#endif

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
#endif
#if defined(NFALLBLOCKS) && NFALLBLOCKS > 0
    for (int j = 0; j < NFALLBLOCKS; j++)
        if (a->fbT[j] != t->fbT[j]) return false;
#endif
#if defined(NCRUMBLES) && NCRUMBLES > 0
    for (int j = 0; j < NCRUMBLES; j++)
        if (a->crT[j] != t->crT[j]) return false;
#endif
#if defined(NDASHBLOCKS) && NDASHBLOCKS > 0
    if (a->dbBroken != t->dbBroken) return false;
#endif
#if defined(NTOUCH) && NTOUCH > 0
    if (a->tsOn != t->tsOn) return false;
#endif
#if defined(HAS_CHASER) && HAS_CHASER
    /* The chasers read the positions she recorded CHASER_DELAY + 0.4 s * index
     * frames ago, so entries older than the longest delay can never be read
     * again; the rest, and the count that indexes them, are live. */
    if (a->chaserTimer != t->chaserTimer) return false;
    for (int d = 0; d <= CHASER_MAX_DELAY; d++) {
        int i = (t->chaserTimer - 1 - d) & CHASER_HIST_MASK;
        if (a->histX[i] != t->histX[i] || a->histY[i] != t->histY[i]) return false;
    }
#endif
#if NZIPMOVERS > 0 || (defined(NFALLBLOCKS) && NFALLBLOCKS > 0) || (defined(NCRUMBLES) && NCRUMBLES > 0) \
    || (defined(NDASHBLOCKS) && NDASHBLOCKS > 0)
    if (a->hopZip != t->hopZip || (t->hopZip && a->hopZipT != t->hopZipT)) return false;
#endif
#if NREFILLS > 0
    for (int k = 0; k < NREFILLS; k++)
        if (a->refillTimer[k] != t->refillTimer[k]) return false;
#endif
    if (!(ign & SF_VARJUMP) && t->varJumpTimer > 0 && !(EQ(varJumpSpeed) && EQ(varJumpLong) && EQ(varJumpShort))) return false;
    if (!(ign & SF_RETENTION) && t->wallSpeedRetentionTimer > 0 && !EQ(wallSpeedRetained)) return false;
    if (!(ign & SF_FORCEMOVE) && t->forceMoveXTimer > 0 && !EQ(forceMoveX)) return false;
    if (!(ign & SF_WALLBOOST) && t->wallBoostTimer > 0 && !EQ(wallBoostDir)) return false;
    if (t->coActive && !(EQ(coStage) && EQ(coWait))) return false;
    if (t->coActive && t->coStage <= 1 && !(EQ(beforeDashSpdX) && EQ(beforeDashSpdY))) return false;
    if (t->state == ST_DASH && !EQ(dashStartedOnGround)) return false;   /* set by DashBegin */
    if (t->state == ST_CLIMB && !EQ(climbNoMoveTimer)) return false;     /* set by ClimbBegin */
    /* both set by dream_dash_begin, and only read in ST_DREAM_DASH */
    if (t->state == ST_DREAM_DASH && !(EQ(dreamDashCanEndTimer) && EQ(dreamJump))) return false;
    return true;
#undef EQI
#undef EQ
}

static bool same_future(const State *a, const State *t) { return same_future_mask(a, t, 0); }

#endif
