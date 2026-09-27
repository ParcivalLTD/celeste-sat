/*
 * celeste.c -- see celeste.h. Function names follow Player.cs / Monocle so the
 * port can be checked side by side with the C# source.
 *
 * Two builds of the same source:
 *   -DREFERENCE   literal port: float timers, pixel-by-pixel Actor movement.
 *   (default)     solver build: timers become exact integer frame counters
 *                 (tables.h, computed with the game's float arithmetic) and
 *                 movement jumps straight to the single tile boundary a move
 *                 can cross. tests/diff.sh checks both builds agree frame by
 *                 frame on random inputs and random rooms.
 *
 * Solver-friendliness notes (both builds):
 *   - Where C# multiplies constants inside a branch (RunAccel * mult * dt with
 *     mult in {1, .65}), the port selects between fully-constant products, so
 *     the float operations are identical but CBMC can fold them.
 *   - Direction vectors (lastAim, DashDir) are stored as integer signs;
 *     diagonals are normalised, so float components come from constants.
 */
#include "celeste.h"
#include "room.h"
#include "tables.h"

#define ROOM_PX_W (ROOM_W * 8)
#define ROOM_PX_H (ROOM_H * 8)

/* Coverage counters for tests/diff.sh (compiled out otherwise). */
#ifdef COVERAGE
enum { C_JUMP, C_SUPER, C_HYPER, C_WALLJUMP, C_SUPERWALLJUMP, C_DASH, C_DASHSLIDE, C_LANDSLIDE,
       C_DASHCORNER_H, C_DASHCORNER_V, C_UPCORNER, C_CEILINGCUT, C_RETAIN, C_DUCKCORRECT,
       C_FLOORSNAP, C_WALLSLIDE, C_FASTFALL, C_DUCKDASH, C_NCOV };
static const char *COV_NAMES[C_NCOV] = { "jump", "super", "hyper", "wall jump", "super wall jump",
       "dash", "dash slide", "landing slide", "dash corner corr. (h)", "dash corner corr. (v)",
       "upward corner corr.", "ceiling var-jump cut", "wall speed retention", "duck correction",
       "dash floor snap", "wall slide", "fast fall", "dash into low gap (duck)" };
static long COVC[C_NCOV];
#define COV(k) (COVC[k]++)
#else
#define COV(k) ((void)0)
#endif

/* The simulator checks these; the solver harness assumes them. */
#ifndef MODEL_ASSUME
#define MODEL_ASSUME(c) ((void)0)
#endif

/* ------------------------------------------------------------------------ */
/* Timers                                                                   */
/* ------------------------------------------------------------------------ */
#ifdef REFERENCE
#define TSET(t, C)  ((t) = (C))
#define TCLR(t)     ((t) = 0.0f)
#define TPOS(t)     ((t) > 0)
#define TDEC(t)     ((t) -= DT)              /* only while TPOS(t) */
#define TLESS(t, C) ((t) < (C))              /* t < C for a timer counting down from its set value */
/* wallSlideTimer */
#define WS_SET(s)   ((s)->wallSlideTimer = WALL_SLIDE_TIME)
#define WS_DEC(s)   ((s)->wallSlideTimer = maxf((s)->wallSlideTimer - DT, 0))
#define WS_POS(s)   ((s)->wallSlideTimer > 0)
#define WS_MAX(s)   (MAX_FALL + (WALL_SLIDE_START_MAX - MAX_FALL) * ((s)->wallSlideTimer / WALL_SLIDE_TIME))
#else
#define TSET(t, C)  ((t) = K_##C)
#define TCLR(t)     ((t) = 0)
#define TPOS(t)     ((t) > 0)
#define TDEC(t)     ((t) -= 1)
#define TLESS(t, C) ((t) < K_##C)
#define WS_SET(s)   ((s)->wallSlideTimer = 0)
#define WS_DEC(s)   ((s)->wallSlideTimer = (s)->wallSlideTimer < WS_KZ ? (s)->wallSlideTimer + 1 : WS_KZ)
#define WS_POS(s)   ((s)->wallSlideTimer < WS_KZ)
#define WS_MAX(s)   (WS_LERP_MAX[(s)->wallSlideTimer])
#endif

/* ------------------------------------------------------------------------ */
/* small helpers (System.Math / Monocle.Calc)                              */
/* ------------------------------------------------------------------------ */
static int signf(float v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }
static int signi(int v)   { return v > 0 ? 1 : (v < 0 ? -1 : 0); }
static float absf(float v) { return v < 0 ? -v : v; }
static float maxf(float a, float b) { return a > b ? a : b; } /* Math.Max */
static float minf(float a, float b) { return a < b ? a : b; } /* Math.Min */

/* Calc.Approach. (val - maxMove) is computed as val + (-maxMove): IEEE
 * subtraction is defined that way, so it is bit-identical, and the solver
 * only needs one adder. */
static float approach(float val, float target, float maxMove)
{
    bool down = val > target;
    float r = val + (down ? -maxMove : maxMove);
    return down ? maxf(r, target) : minf(r, target);
}

#ifndef REFERENCE
/* Math.Round(x, MidpointRounding.ToEven) for |x| <= 8.5 (the only range the
 * movement counter can be in), written as comparisons against constants so
 * the solver needs no float->int conversion. Ties go to the even neighbour.
 * tests/diff.sh checks it against the general version. */
static int round_even(float x)
{
    MODEL_ASSUME(x >= -8.5f && x <= 8.5f);
    int r = 0;
    if (x > 0.5f)  r = 1;
    if (x >= 1.5f) r = 2;
    if (x > 2.5f)  r = 3;
    if (x >= 3.5f) r = 4;
    if (x > 4.5f)  r = 5;
    if (x >= 5.5f) r = 6;
    if (x > 6.5f)  r = 7;
    if (x >= 7.5f) r = 8;
    if (x < -0.5f)  r = -1;
    if (x <= -1.5f) r = -2;
    if (x < -2.5f)  r = -3;
    if (x <= -3.5f) r = -4;
    if (x < -4.5f)  r = -5;
    if (x <= -5.5f) r = -6;
    if (x < -6.5f)  r = -7;
    if (x <= -7.5f) r = -8;
    return r;
}
#else
/* Math.Round(x, MidpointRounding.ToEven) for |x| < 2^22 */
static int round_even(float x)
{
    int t = (int)x;                 /* truncates toward zero */
    float frac = x - (float)t;      /* exact for |x| < 2^23 */
    if (frac > 0.5f) return t + 1;
    if (frac < -0.5f) return t - 1;
    if (frac == 0.5f) return (t & 1) ? t + 1 : t;
    if (frac == -0.5f) return (t & 1) ? t - 1 : t;
    return t;
}
#endif

/* component of a direction encoded as integer signs (diagonals normalised),
 * multiplied by a constant speed exactly like (dir * speed) in C#. */
#define DIR_TIMES(comp, other, SPEED)                                          \
    ((comp) == 0 ? 0.0f                                                        \
     : ((other) != 0 ? ((comp) > 0 ? (DIAG * (SPEED)) : ((-DIAG) * (SPEED)))  \
                     : ((comp) > 0 ? (SPEED) : (-(SPEED)))))

/* ------------------------------------------------------------------------ */
/* Collision against the room's SolidTiles grid (Monocle Grid.Collide)       */
/* ROOM_COLS[c] has bit r set when tile (c, r) is solid; outside the grid is */
/* air (Grid.CheckRect clamps to the grid).                                  */
/* ------------------------------------------------------------------------ */
static int floor8(int v) { return v >> 3; } /* arithmetic shift == floor division by 8 */

static unsigned col_bits(int c)
{
    if (c < 0 || c >= ROOM_W) return 0;
    return ROOM_COLS[c];
}

#ifdef REFERENCE
/* bitmask of tile rows r0..r1 (inclusive), clipped to the grid */
static unsigned row_span(int r0, int r1)
{
    if (r0 < 0) r0 = 0;
    if (r1 > ROOM_H - 1) r1 = ROOM_H - 1;
    if (r1 < r0) return 0;
    unsigned upto = (r1 >= 31) ? 0xFFFFFFFFu : ((1u << (r1 + 1)) - 1u);
    unsigned below = (1u << r0) - 1u;
    return upto & ~below;
}

/* hitbox 8 x h with offset (-4, -h), placed at (x, y) */
static bool collide_box(int x, int y, int h)
{
    unsigned rows = row_span(floor8(y - h), floor8(y - 1));
    return ((col_bits(floor8(x - 4)) | col_bits(floor8(x + 3))) & rows) != 0;
}
#define LOAD_WINDOW(s) ((void)0)
#else
/* Solver build: every collision check during one frame lies within a few
 * tiles of where the frame started (moves are <= 8 px, corner corrections
 * <= 4 px), so each frame first copies an 8x8-tile window of the room around
 * the player and all checks read that window instead of the whole room.
 * MODEL_ASSUME guards the bounds (the simulator asserts them). */
static int WX0, WY0;                 /* window origin, in tiles */
static unsigned char WCOL[8];        /* WCOL[i] bit j: tile (WX0+i, WY0+j) solid */

static void load_window(const State *s)
{
    WX0 = floor8(s->x - 28);
    WY0 = floor8(s->y - 32);
    for (int i = 0; i < 8; i++) {
        unsigned long long c = (unsigned long long)col_bits(WX0 + i) << 8;  /* 8 rows of padding above */
        int sh = WY0 + 8;
        MODEL_ASSUME(sh >= 0 && sh < 56);
        WCOL[i] = (unsigned char)(c >> sh);
    }
}
#define LOAD_WINDOW(s) load_window(s)

static unsigned span8(int r0, int r1) { return (0xFFu << r0) & (0xFFu >> (7 - r1)); }

static unsigned wcol(int c)          /* column c (room coordinates) of the window */
{
    int i = c - WX0;
    MODEL_ASSUME(i >= 0 && i < 8);
    return WCOL[i];
}

static bool collide_box(int x, int y, int h)
{
    int r0 = floor8(y - h) - WY0, r1 = floor8(y - 1) - WY0;
    MODEL_ASSUME(r0 >= 0 && r1 < 8);
    return ((wcol(floor8(x - 4)) | wcol(floor8(x + 3))) & span8(r0, r1)) != 0;
}
#endif

static int collider_h(const State *s) { return s->ducking ? HB_DUCK_H : HB_NORMAL_H; }

/* CollideCheck<Solid>(at) with the current collider */
static bool collide_at(const State *s, int x, int y) { return collide_box(x, y, collider_h(s)); }

/* ------------------------------------------------------------------------ */
/* Actor movement                                                           */
/* ------------------------------------------------------------------------ */
#define MAX_PIXELS_H 8   /* |Speed.X| <= ~390 px/s  ->  <= 7 px per frame */
#define MAX_PIXELS_V 6   /* |Speed.Y| <= 240 px/s   ->  <= 5 px per frame */

static void on_collide_h(State *s);
static void on_collide_v(State *s);

#ifdef REFERENCE
/* Actor.MoveHExact / MoveVExact without callback: literal pixel stepping */
static bool move_h_exact_plain(State *s, int move)
{
    int dir = signi(move);
    bool hit = false;
    MODEL_ASSUME(move >= -MAX_PIXELS_H && move <= MAX_PIXELS_H);
    for (int i = 0; i < MAX_PIXELS_H; i++) {
        if (move == 0 || hit) break;
        if (collide_at(s, s->x + dir, s->y)) hit = true;
        else { s->x += dir; move -= dir; }
    }
    if (hit) s->remX = 0.0f;
    return hit;
}

static bool move_v_exact_plain(State *s, int move)
{
    int dir = signi(move);
    bool hit = false;
    MODEL_ASSUME(move >= -MAX_PIXELS_V && move <= MAX_PIXELS_V);
    for (int i = 0; i < MAX_PIXELS_V; i++) {
        if (move == 0 || hit) break;
        if (collide_at(s, s->x, s->y + dir)) hit = true;
        else { s->y += dir; move -= dir; }
    }
    if (hit) s->remY = 0.0f;
    return hit;
}
#else
/* Same result without the pixel loop. The player never overlaps a solid, so
 * while moving n <= 8 pixels the hitbox can only run into the next tile
 * column (row) beyond its leading edge; if that tile column is solid within
 * the hitbox's rows and the move reaches it, the player stops flush with it. */
static bool move_h_exact_plain(State *s, int move)
{
    MODEL_ASSUME(move >= -MAX_PIXELS_H && move <= MAX_PIXELS_H);
    if (move == 0) return false;
    int h = collider_h(s);
    int r0 = floor8(s->y - h) - WY0, r1 = floor8(s->y - 1) - WY0;
    MODEL_ASSUME(r0 >= 0 && r1 < 8);
    unsigned rows = span8(r0, r1);
    if (move > 0) {
        int b = ((s->x + 4 + 7) >> 3) << 3;          /* first tile boundary at/after right edge */
        if (b < s->x + 4 + move && (wcol(b >> 3) & rows)) {
            s->x = b - 4;
            s->remX = 0.0f;
            return true;
        }
    } else {
        int a = ((s->x - 4) >> 3) << 3;              /* last tile boundary at/before left edge */
        if (s->x - 4 + move < a && (wcol((a >> 3) - 1) & rows)) {
            s->x = a + 4;
            s->remX = 0.0f;
            return true;
        }
    }
    s->x += move;
    return false;
}

static bool move_v_exact_plain(State *s, int move)
{
    MODEL_ASSUME(move >= -MAX_PIXELS_V && move <= MAX_PIXELS_V);
    if (move == 0) return false;
    int h = collider_h(s);
    unsigned cols = wcol(floor8(s->x - 4)) | wcol(floor8(s->x + 3));
    if (move > 0) {
        int r = (s->y + 7) >> 3;                     /* first tile row at/below the feet */
        MODEL_ASSUME(r - WY0 >= 0 && r - WY0 < 8);
        if ((r << 3) < s->y + move && ((cols >> (r - WY0)) & 1u)) {
            s->y = r << 3;
            s->remY = 0.0f;
            return true;
        }
    } else {
        int a = ((s->y - h) >> 3) << 3;              /* last tile boundary at/above the head */
        int r = (a >> 3) - 1;
        MODEL_ASSUME(r - WY0 >= 0 && r - WY0 < 8);
        if (s->y - h + move < a && ((cols >> (r - WY0)) & 1u)) {
            s->y = a + h;
            s->remY = 0.0f;
            return true;
        }
    }
    s->y += move;
    return false;
}
#endif

/* Actor.MoveH / MoveV with the player's OnCollideH / OnCollideV callbacks.
 * (C# calls onCollide from inside the loop and returns right after, so
 * calling it after the loop is the same.) */
static void move_h(State *s, float amount)
{
    s->remX += amount;
    int move = round_even(s->remX);
    if (move == 0) return;
    s->remX -= (float)move;
    if (move_h_exact_plain(s, move)) on_collide_h(s);
}

static void move_v(State *s, float amount)
{
    s->remY += amount;
    int move = round_even(s->remY);
    if (move == 0) return;
    s->remY -= (float)move;
    if (move_v_exact_plain(s, move)) on_collide_v(s);
}

/* MoveH(float) with no callback (used by duck correction) */
static void move_h_plain(State *s, float amount)
{
    s->remX += amount;
    int move = round_even(s->remX);
    if (move == 0) return;
    s->remX -= (float)move;
    move_h_exact_plain(s, move);
}

/* ------------------------------------------------------------------------ */
/* Player helpers                                                           */
/* ------------------------------------------------------------------------ */
static bool can_unduck_at(const State *s, int x, int y)
{
    if (!s->ducking) return true;
    return !collide_box(x, y, HB_NORMAL_H);
}
static bool can_unduck(const State *s) { return can_unduck_at(s, s->x, s->y); }
static bool duck_free_at(int x, int y) { return !collide_box(x, y, HB_DUCK_H); }

/* level.Bounds is the room: [0, ROOM_PX_W) x [0, ROOM_PX_H) */
static bool climb_bounds_check(const State *s, int dir)
{
    int left = s->x - 4, right = s->x + 4;
    return left + dir * CLIMB_CHECK_DIST >= 0 && right + dir * CLIMB_CHECK_DIST < ROOM_PX_W;
}

static bool wall_jump_check(const State *s, int dir)
{
    return climb_bounds_check(s, dir) && collide_at(s, s->x + dir * WALL_JUMP_CHECK_DIST, s->y);
}

static bool jump_pressed(const State *s) { return TPOS(s->jumpBuf) || s->jumpEdge; }
static bool dash_pressed(const State *s) { return TPOS(s->dashBuf) || s->dashEdge; }
static bool dash_attacking(const State *s) { return TPOS(s->dashAttackTimer); }

/* ------------------------------------------------------------------------ */
/* Jumps                                                                    */
/* ------------------------------------------------------------------------ */
static void jump(State *s)
{
    COV(C_JUMP);
    TCLR(s->jumpBuf);                     /* Input.Jump.ConsumeBuffer() */
    TCLR(s->jumpGraceTimer);
    TSET(s->varJumpTimer, VAR_JUMP_TIME);
    s->varJumpLong = false;
    s->autoJump = false;
    TCLR(s->dashAttackTimer);
    WS_SET(s);
    /* Speed.X += JumpHBoost * moveX */
    s->spdX += (s->moveX > 0 ? JUMP_H_BOOST * 1.0f : (s->moveX < 0 ? JUMP_H_BOOST * -1.0f : JUMP_H_BOOST * 0.0f));
    s->spdY = JUMP_SPEED;
    s->varJumpSpeed = s->spdY;
}

static void super_jump(State *s)
{
    COV(C_SUPER);
    TCLR(s->jumpBuf);
    TCLR(s->jumpGraceTimer);
    TSET(s->varJumpTimer, VAR_JUMP_TIME);
    s->varJumpLong = false;
    s->autoJump = false;
    TCLR(s->dashAttackTimer);
    WS_SET(s);
    s->spdX = s->facing > 0 ? SUPER_JUMP_H : -SUPER_JUMP_H;
    s->spdY = JUMP_SPEED;
    if (s->ducking) {                     /* hyper */
        COV(C_HYPER);
        s->ducking = false;
        s->spdX = s->facing > 0 ? SUPER_JUMP_H * DUCK_SUPER_JUMP_X_MULT
                                : (-SUPER_JUMP_H) * DUCK_SUPER_JUMP_X_MULT;
        s->spdY = JUMP_SPEED * DUCK_SUPER_JUMP_Y_MULT;
    }
    s->varJumpSpeed = s->spdY;
}

static void wall_jump(State *s, int dir)
{
    COV(C_WALLJUMP);
    s->ducking = false;
    TCLR(s->jumpBuf);
    TCLR(s->jumpGraceTimer);
    TSET(s->varJumpTimer, VAR_JUMP_TIME);
    s->varJumpLong = false;
    s->autoJump = false;
    TCLR(s->dashAttackTimer);
    WS_SET(s);
    if (s->moveX != 0) {
        s->forceMoveX = dir;
        TSET(s->forceMoveXTimer, WALL_JUMP_FORCE_TIME);
    }
    s->spdX = dir > 0 ? WALL_JUMP_H_SPEED : -WALL_JUMP_H_SPEED;
    s->spdY = JUMP_SPEED;
    s->varJumpSpeed = s->spdY;
}

static void super_wall_jump(State *s, int dir)
{
    COV(C_SUPERWALLJUMP);
    s->ducking = false;
    TCLR(s->jumpBuf);
    TCLR(s->jumpGraceTimer);
    TSET(s->varJumpTimer, SUPER_WALL_JUMP_VAR_TIME);
    s->varJumpLong = true;
    s->autoJump = false;
    TCLR(s->dashAttackTimer);
    WS_SET(s);
    s->spdX = dir > 0 ? SUPER_WALL_JUMP_H : -SUPER_WALL_JUMP_H;
    s->spdY = SUPER_WALL_JUMP_SPEED;
    s->varJumpSpeed = s->spdY;
}

/* ------------------------------------------------------------------------ */
/* Collision callbacks                                                      */
/* ------------------------------------------------------------------------ */
static void on_collide_h(State *s)
{
    /* dash corner correction */
    if (s->state == ST_DASH) {
        int sx = signf(s->spdX);
        if (s->onGround && duck_free_at(s->x + sx, s->y)) {
            COV(C_DUCKDASH);
            s->ducking = true;
            return;
        } else if (s->spdY == 0 && s->spdX != 0) {
            /* for i in 1..4, j in {+1,-1}: first free (sx, i*j) */
            int dy = 0;
            for (int i = 1; i <= DASH_CORNER_CORRECTION; i++) {
                if (dy != 0) break;
                if (!collide_at(s, s->x + sx, s->y + i)) dy = i;
                else if (!collide_at(s, s->x + sx, s->y - i)) dy = -i;
            }
            if (dy != 0) {
                move_v_exact_plain(s, dy);
                COV(C_DASHCORNER_H);
                move_h_exact_plain(s, sx);
                return;
            }
        }
    }

    /* speed retention */
    if (!TPOS(s->wallSpeedRetentionTimer)) {
        s->wallSpeedRetained = s->spdX;
        TSET(s->wallSpeedRetentionTimer, WALL_SPEED_RETENTION_TIME);
    }

    s->spdX = 0;
    TCLR(s->dashAttackTimer);
}

static void on_collide_v(State *s)
{
    if (s->spdY > 0) {
        /* dash corner correction */
        if (s->state == ST_DASH && !s->dashStartedOnGround) {
            int dx = 0;                         /* first i with !OnGround(Position + (i,0)) */
            if (s->spdX <= 0) {
                for (int i = 1; i <= DASH_CORNER_CORRECTION; i++) {
                    if (dx != 0) break;
                    if (!collide_at(s, s->x - i, s->y + 1)) dx = -i;
                }
            }
            if (dx == 0 && s->spdX >= 0) {
                for (int i = 1; i <= DASH_CORNER_CORRECTION; i++) {
                    if (dx != 0) break;
                    if (!collide_at(s, s->x + i, s->y + 1)) dx = i;
                }
            }
            if (dx != 0) {
                move_h_exact_plain(s, dx);
                move_v_exact_plain(s, 1);
                COV(C_DASHCORNER_V);
                return;
            }
        }

        /* dash slide (also applies when landing after a down-diagonal dash) */
        if (s->dashDirX != 0 && s->dashDirY > 0 && s->spdY > 0) {
            COV(C_LANDSLIDE);
            s->dashDirX = signi(s->dashDirX);
            s->dashDirY = 0;
            s->spdY = 0;
            s->spdX *= DODGE_SLIDE_SPEED_MULT;
            s->ducking = true;
        }
    } else {
        if (s->spdY < 0) {
            /* upward corner correction */
            int dx = 0;
            if (s->spdX <= 0) {
                for (int i = 1; i <= UPWARD_CORNER_CORRECTION; i++) {
                    if (dx != 0) break;
                    if (!collide_at(s, s->x - i, s->y - 1)) dx = -i;
                }
            }
            if (dx == 0 && s->spdX >= 0) {
                for (int i = 1; i <= UPWARD_CORNER_CORRECTION; i++) {
                    if (dx != 0) break;
                    if (!collide_at(s, s->x + i, s->y - 1)) dx = i;
                }
            }
            if (dx != 0) {                      /* Position += (dx, -1) */
                COV(C_UPCORNER);
                s->x += dx;
                s->y -= 1;
                return;
            }

            /* if (varJumpTimer < VarJumpTime - CeilingVarJumpGrace) varJumpTimer = 0 */
#ifdef REFERENCE
            if (s->varJumpTimer < VAR_JUMP_TIME - CEILING_VAR_JUMP_GRACE) {
                if (s->varJumpTimer > 0) COV(C_CEILINGCUT);
                s->varJumpTimer = 0;
            }
#else
            if (s->varJumpTimer <= (s->varJumpLong ? VJ_SUPER_WALL_JUMP_VAR_TIME : VJ_VAR_JUMP_TIME))
                s->varJumpTimer = 0;
#endif
        }
    }

    TCLR(s->dashAttackTimer);
    s->spdY = 0;
}

/* ------------------------------------------------------------------------ */
/* State machine                                                            */
/* ------------------------------------------------------------------------ */
static void normal_begin(State *s) { s->maxFall = MAX_FALL; }
static void normal_end(State *s)   { TCLR(s->wallSpeedRetentionTimer); /* wallBoostTimer, hopWaitX */ }

static void dash_begin(State *s)
{
    COV(C_DASH);
    s->dashStartedOnGround = s->onGround;
    if (TLESS(s->freezeTimer, DASH_FREEZE_TIME)) TSET(s->freezeTimer, DASH_FREEZE_TIME); /* Celeste.Freeze(.05f) */
    TSET(s->dashCooldownTimer, DASH_COOLDOWN);
    TSET(s->dashRefillCooldownTimer, DASH_REFILL_COOLDOWN);
    WS_SET(s);
    TSET(s->dashAttackTimer, DASH_ATTACK_TIME);
    s->beforeDashSpdX = s->spdX;
    s->beforeDashSpdY = s->spdY;
    s->spdX = 0;
    s->spdY = 0;
    s->dashDirX = 0;
    s->dashDirY = 0;
    if (!s->onGround && s->ducking && can_unduck(s)) s->ducking = false;
}

static void set_state(State *s, int next)
{
    if (s->state == next) return;
    int prev = s->state;
    s->state = next;
    if (prev == ST_NORMAL) normal_end(s);        /* DashEnd only fires dash events */
    if (next == ST_NORMAL) {
        normal_begin(s);
        s->coActive = false;                     /* currentCoroutine.Cancel() */
        TCLR(s->coWait);
    } else {
        dash_begin(s);
        s->coActive = true;                      /* currentCoroutine.Replace(DashCoroutine()) */
        s->coStage = 0;
        TCLR(s->coWait);
    }
}

static int start_dash(State *s)
{
    s->dashes = s->dashes - 1 > 0 ? s->dashes - 1 : 0;
    TCLR(s->dashBuf);                            /* Input.Dash.ConsumeBuffer() */
    return ST_DASH;
}

static int normal_update(State *s, Input in)
{
    /* (lift boost, grabbing and climbing are not modelled) */

    /* Dashing */
    if (dash_pressed(s) && !TPOS(s->dashCooldownTimer) && s->dashes > 0)
        return start_dash(s);

    /* Ducking */
    if (s->ducking) {
        if (s->onGround && in.my != 1) {
            if (can_unduck(s)) {
                s->ducking = false;
            } else if (s->spdX == 0) {
                int d = 0;
                for (int i = DUCK_CORRECT_CHECK; i > 0; i--) {
                    if (d != 0) break;
                    if (can_unduck_at(s, s->x + i, s->y)) d = 1;
                    else if (can_unduck_at(s, s->x - i, s->y)) d = -1;
                }
                if (d != 0) {
                    COV(C_DUCKCORRECT);
                    move_h_plain(s, d > 0 ? DUCK_CORRECT_SLIDE * DT : -DUCK_CORRECT_SLIDE * DT);
                }
            }
        }
    } else if (s->onGround && in.my == 1 && s->spdY >= 0) {
        s->ducking = true;
    }

    /* Running and friction (branches select the arguments of one Approach) */
    {
        float target, step;
        if (s->ducking && s->onGround) {
            target = 0.0f;
            step = DUCK_FRICTION * DT;
        } else {
            target = s->moveX > 0 ? MAX_RUN * 1.0f : (s->moveX < 0 ? MAX_RUN * -1.0f : MAX_RUN * 0.0f);
            if (absf(s->spdX) > MAX_RUN && signf(s->spdX) == s->moveX)
                step = s->onGround ? RUN_REDUCE * 1.0f * DT : RUN_REDUCE * AIR_MULT * DT;
            else
                step = s->onGround ? RUN_ACCEL * 1.0f * DT : RUN_ACCEL * AIR_MULT * DT;
        }
        s->spdX = approach(s->spdX, target, step);
    }

    /* Vertical: current max fall speed */
    if (s->maxFall > MAX_FALL) COV(C_FASTFALL);
    s->maxFall = approach(s->maxFall, (in.my == 1 && s->spdY >= MAX_FALL) ? FAST_MAX_FALL : MAX_FALL,
                          FAST_MAX_ACCEL * DT);

    /* Gravity */
    if (!s->onGround) {
        float max = s->maxFall;

        /* wall slide (grab is not modelled, so only moveX == Facing) */
        if (s->moveX == s->facing && in.my != 1) {
            if (s->spdY >= 0 && WS_POS(s) && climb_bounds_check(s, s->facing)
                && collide_at(s, s->x + s->facing, s->y) && can_unduck(s)) {
                s->ducking = false;
                s->wallSlideDir = s->facing;
            }
            if (s->wallSlideDir != 0)
                max = WS_MAX(s);
            if (s->wallSlideDir != 0) COV(C_WALLSLIDE);          /* MathHelper.Lerp(MaxFall, WallSlideStartMax, t / WallSlideTime) */
        }

        bool half = absf(s->spdY) < HALF_GRAV_THRESHOLD && (in.jump || s->autoJump);
        s->spdY = approach(s->spdY, max, half ? GRAVITY * 0.5f * DT : GRAVITY * 1.0f * DT);
    }

    /* Variable jumping */
    if (TPOS(s->varJumpTimer)) {
        if (s->autoJump || in.jump)
            s->spdY = minf(s->spdY, s->varJumpSpeed);
        else
            TCLR(s->varJumpTimer);
    }

    /* Jumping */
    if (jump_pressed(s)) {
        if (TPOS(s->jumpGraceTimer)) {
            jump(s);
        } else if (can_unduck(s)) {
            if (wall_jump_check(s, 1)) {
                if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1)
                    super_wall_jump(s, -1);
                else
                    wall_jump(s, -1);
            } else if (wall_jump_check(s, -1)) {
                if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1)
                    super_wall_jump(s, 1);
                else
                    wall_jump(s, 1);
            }
        }
    }

    return ST_NORMAL;
}

static int dash_update(State *s)
{
    if (s->dashDirY == 0) {
        /* Super jump */
        if (can_unduck(s) && jump_pressed(s) && TPOS(s->jumpGraceTimer)) {
            super_jump(s);
            return ST_NORMAL;
        }
    }

    if (s->dashDirX == 0 && s->dashDirY == -1) {
        if (jump_pressed(s) && can_unduck(s)) {
            if (wall_jump_check(s, 1))       { super_wall_jump(s, -1); return ST_NORMAL; }
            else if (wall_jump_check(s, -1)) { super_wall_jump(s, 1);  return ST_NORMAL; }
        }
    } else {
        if (jump_pressed(s) && can_unduck(s)) {
            if (wall_jump_check(s, 1))       { wall_jump(s, -1); return ST_NORMAL; }
            else if (wall_jump_check(s, -1)) { wall_jump(s, 1);  return ST_NORMAL; }
        }
    }

    return ST_DASH;
}

/* body of DashCoroutine between 'yield return null' and 'yield return DashTime' */
static void dash_coroutine_body(State *s)
{
    int dx = s->aimX, dy = s->aimY;
    float nsx = DIR_TIMES(dx, dy, DASH_SPEED);
    float nsy = DIR_TIMES(dy, dx, DASH_SPEED);
    if (signf(s->beforeDashSpdX) == signf(nsx) && absf(s->beforeDashSpdX) > absf(nsx))
        nsx = s->beforeDashSpdX;
    s->spdX = nsx;
    s->spdY = nsy;

    s->dashDirX = dx;
    s->dashDirY = dy;
    if (s->dashDirX != 0) s->facing = s->dashDirX;

    /* dash slide */
    if (s->onGround && s->dashDirX != 0 && s->dashDirY > 0 && s->spdY > 0) {
        COV(C_DASHSLIDE);
        s->dashDirX = signi(s->dashDirX);
        s->dashDirY = 0;
        s->spdY = 0;
        s->spdX *= DODGE_SLIDE_SPEED_MULT;
        s->ducking = true;
    }
}

/* end of DashCoroutine after the DashTime wait */
static void dash_coroutine_end(State *s)
{
    s->autoJump = true;
    if (s->dashDirY <= 0) {
        /* Speed = DashDir * EndDashSpeed; if (Speed.Y < 0) Speed.Y *= EndDashUpMult;
         * written so both products stay constant-foldable (Speed.Y < 0 <=> DashDir.Y < 0) */
        s->spdX = DIR_TIMES(s->dashDirX, s->dashDirY, END_DASH_SPEED);
        s->spdY = s->dashDirY < 0
                ? (s->dashDirX != 0 ? ((-DIAG) * END_DASH_SPEED) * END_DASH_UP_MULT
                                    : (-END_DASH_SPEED) * END_DASH_UP_MULT)
                : 0.0f;
    } else if (s->spdY < 0) {
        s->spdY *= END_DASH_UP_MULT;
    }
    set_state(s, ST_NORMAL);
}

/* Monocle Coroutine.Update for the dash coroutine */
static void coroutine_update(State *s)
{
    if (TPOS(s->coWait)) {
        TDEC(s->coWait);
        return;
    }
    if (s->coStage == 0) {          /* runs to 'yield return null' */
        s->coStage = 1;
    } else if (s->coStage == 1) {   /* runs to 'yield return DashTime' */
        dash_coroutine_body(s);
        s->coStage = 2;
        TSET(s->coWait, DASH_TIME);
    } else {
        dash_coroutine_end(s);      /* changes state -> coroutine cancelled */
    }
}

/* ------------------------------------------------------------------------ */
/* Player.Update                                                            */
/* ------------------------------------------------------------------------ */
static void player_update(State *s, Input in)
{
    LOAD_WINDOW(s);

    /* Get ground */
    if (s->spdY >= 0) s->onGround = collide_at(s, s->x, s->y + 1);
    else s->onGround = false;

    /* Wall slide */
    if (s->wallSlideDir != 0) {
        WS_DEC(s);
        s->wallSlideDir = 0;
    }

    /* After dash */
    if (s->onGround) {
        s->autoJump = false;
        WS_SET(s);
    }

    /* Dash attack */
    if (TPOS(s->dashAttackTimer)) TDEC(s->dashAttackTimer);

    /* Jump grace */
    if (s->onGround) TSET(s->jumpGraceTimer, JUMP_GRACE_TIME);
    else if (TPOS(s->jumpGraceTimer)) TDEC(s->jumpGraceTimer);

    /* Dashes */
    if (TPOS(s->dashCooldownTimer)) TDEC(s->dashCooldownTimer);
    if (TPOS(s->dashRefillCooldownTimer)) TDEC(s->dashRefillCooldownTimer);
    else if (s->onGround && s->dashes < MAX_DASHES) s->dashes = MAX_DASHES;

    /* Var jump */
    if (TPOS(s->varJumpTimer)) TDEC(s->varJumpTimer);

    /* Force move X */
    if (TPOS(s->forceMoveXTimer)) {
        TDEC(s->forceMoveXTimer);
        s->moveX = s->forceMoveX;
    } else {
        s->moveX = in.mx;
    }

    /* Facing */
    if (s->moveX != 0) s->facing = s->moveX;

    /* Aiming: Input.GetAimVector(Facing), 8-way digital */
    if (in.mx == 0 && in.my == 0) { s->aimX = s->facing; s->aimY = 0; }
    else { s->aimX = in.mx; s->aimY = in.my; }

    /* Wall speed retention */
    if (TPOS(s->wallSpeedRetentionTimer)) {
        int rs = signf(s->wallSpeedRetained);
        if (signf(s->spdX) == -rs)
            TCLR(s->wallSpeedRetentionTimer);
        else if (!collide_at(s, s->x + rs, s->y)) {
            s->spdX = s->wallSpeedRetained;
            COV(C_RETAIN);
            TCLR(s->wallSpeedRetentionTimer);
        } else
            TDEC(s->wallSpeedRetentionTimer);
    }

    /* base.Update() -> StateMachine.Update() */
    int next = (s->state == ST_NORMAL) ? normal_update(s, in) : dash_update(s);
    set_state(s, next);
    if (s->coActive) coroutine_update(s);

    /* Dash floor snapping */
    if (!s->onGround && dash_attacking(s) && s->dashDirY == 0) {
        if (collide_at(s, s->x, s->y + DASH_V_FLOOR_SNAP_DIST)) {
            COV(C_FLOORSNAP);
            move_v_exact_plain(s, DASH_V_FLOOR_SNAP_DIST);
        }
    }

    /* Falling unducking */
    if (s->spdY > 0 && can_unduck(s) && !s->onGround) s->ducking = false;

    /* Physics */
    move_h(s, s->spdX * DT);
    move_v(s, s->spdY * DT);

    /* Level.EnforceBounds */
    {
        int left = s->x - 4, right = s->x + 4, top = s->y - collider_h(s), bottom = s->y;
        if (left < 0) {                 /* no room to the left: clamp */
            s->x = 4;
            s->spdX = 0;
        }
        if (right > ROOM_PX_W) {
            if (top >= 0 && bottom < ROOM_PX_H) { s->exited = true; return; } /* transition */
            s->x = ROOM_PX_W - 4;
            s->spdX = 0;
        }
        top = s->y - collider_h(s);
        if (top < 0) {                  /* no room above: clamp */
            s->y = collider_h(s);
            s->spdY = 0;
        }
        if (top > ROOM_PX_H + 4) s->dead = true; /* fell out of the room */
    }
}

/* ------------------------------------------------------------------------ */
/* Public API                                                               */
/* ------------------------------------------------------------------------ */
void celeste_init(State *s, int spawnX, int spawnY)
{
    State z = {0};
    *s = z;
    s->x = spawnX;
    s->y = spawnY;
    s->state = ST_NORMAL;
    s->facing = 1;
    s->dashes = MAX_DASHES;
    s->maxFall = MAX_FALL;
    WS_SET(s);
    s->aimX = 1;
}

/* One frame: Engine.Update -> MInput.Update, then either a freeze frame or a
 * full scene update (only the player is simulated). */
void celeste_step(State *s, Input in)
{
    if (s->exited || s->dead) return;

    /* VirtualButton.Update (runs every frame, including freeze frames):
     * bufferCounter -= dt; if (pressed) bufferCounter = BufferTime; if (!held) bufferCounter = 0 */
    if (TPOS(s->jumpBuf)) TDEC(s->jumpBuf);
    s->jumpEdge = in.jump && !s->prevJump;
    if (s->jumpEdge) TSET(s->jumpBuf, INPUT_BUFFER_TIME);
    if (!in.jump) TCLR(s->jumpBuf);
    s->prevJump = in.jump;

    if (TPOS(s->dashBuf)) TDEC(s->dashBuf);
    s->dashEdge = in.dash && !s->prevDash;
    if (s->dashEdge) TSET(s->dashBuf, INPUT_BUFFER_TIME);
    if (!in.dash) TCLR(s->dashBuf);
    s->prevDash = in.dash;

    /* Engine freeze (dash freeze frames) */
    if (TPOS(s->freezeTimer)) {
#ifdef REFERENCE
        s->freezeTimer = maxf(s->freezeTimer - DT, 0);
#else
        TDEC(s->freezeTimer);
#endif
        return;
    }

    player_update(s, in);
}
