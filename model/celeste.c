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
#ifdef ROOM_HEADER
#include ROOM_HEADER
#else
#include "room.h"
#endif
#include "tables.h"

/* One room per build, or (MODEL_PREFIX) one of several rooms in the same
 * program: then the API is static and exported under prefixed names. */
#ifdef MODEL_PREFIX
#define MODEL_API static
#else
#define MODEL_API
#endif

#define ROOM_PX_W (ROOM_W * 8)
#define ROOM_PX_H (ROOM_H * 8)

/* Coverage counters for tests/diff.sh (compiled out otherwise). */
#ifdef COVERAGE
enum { C_JUMP, C_SUPER, C_HYPER, C_WALLJUMP, C_SUPERWALLJUMP, C_DASH, C_DASHSLIDE, C_LANDSLIDE,
       C_DASHCORNER_H, C_DASHCORNER_V, C_UPCORNER, C_CEILINGCUT, C_RETAIN, C_DUCKCORRECT,
       C_FLOORSNAP, C_WALLSLIDE, C_FASTFALL, C_DUCKDASH,
       C_EXIT_L, C_EXIT_R, C_EXIT_U, C_EXIT_D, C_TOPCLAMP, C_FELL,
       C_SPIKE_U, C_SPIKE_D, C_SPIKE_L, C_SPIKE_R,
       C_CLIMB, C_CLIMBUP, C_CLIMBDOWN, C_SLIP, C_CLIMBJUMP, C_WALLBOOST, C_CLIMBHOP, C_HOPWAIT,
       C_TIRED, C_NOSPIKEREFILL, C_HOPBLOCKED,
       C_JTLAND, C_JTASSIST, C_JTNUDGE, C_JTSNAP, C_SPRING, C_LEAVE,
       C_DASHCLIMBJUMP, C_CROUCHDASH, C_ZIPSTART, C_ZIPRIDE, C_ZIPPUSH, C_ZIPNUDGE, C_SQUISH, C_NCOV };
static const char *COV_NAMES[C_NCOV] = { "jump", "super", "hyper", "wall jump", "super wall jump",
       "dash", "dash slide", "landing slide", "dash corner corr. (h)", "dash corner corr. (v)",
       "upward corner corr.", "ceiling var-jump cut", "wall speed retention", "duck correction",
       "dash floor snap", "wall slide", "fast fall", "dash into low gap (duck)",
       "exit left", "exit right", "exit up", "exit down", "top clamp (-24 px)", "fell out (death)",
       "spikes up (death)", "spikes down (death)", "spikes left (death)", "spikes right (death)",
       "grab (climb begin)", "climbing up", "climbing down", "climb slip", "climb jump", "wall boost",
       "climb hop", "hop wait", "out of stamina", "no refill (on spikes)", "hop blocked (spikes)",
       "jump-through landing", "jump-through assist", "dash jump-through nudge", "floor snap onto jump-through",
       "spring", "left for another room (fail)", "climb jump out of a dash", "dash starts ducked",
       "zip mover starts", "carried by a zip mover", "pushed by a zip mover", "zip mover edge nudge (1 px down)",
       "squished (death)" };
static long COVC[C_NCOV];
#define COV(k) (COVC[k]++)
#else
#define COV(k) ((void)0)
#endif

/* The simulator checks these; the solver harness assumes them. */
#ifndef MODEL_ASSUME
#define MODEL_ASSUME(c) ((void)0)
#endif
/* Called at the start of every non-frozen frame, after the collision window
 * is loaded; the solver harness uses it for symmetry breaking. */
#ifndef FRAME_HOOK
#define FRAME_HOOK(s, in) ((void)0)
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
#define TDEC_FREE(t) ((t) -= DT)             /* decremented every frame, may go below 0 */
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
#define TDEC_FREE(t) ((t) > 0 ? ((t) -= 1) : 0)  /* only "<= 0" is ever tested */
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

/* the largest whole-pixel move in one frame: 8 (~390 px/s), or 16 in rooms
 * with moving solids (up to 250 px/s of lift boost on top) */
#if NZIPMOVERS > 0
#define ROUND_MAX 16
#else
#define ROUND_MAX 8
#endif

#ifndef REFERENCE
/* Math.Round(x, MidpointRounding.ToEven) for |x| <= ROUND_MAX + 0.5 (the only
 * range the movement counter can be in), written as comparisons against
 * constants so the solver needs no float->int conversion. Ties go to the even
 * neighbour. tests/diff.sh checks it against the general version. */
static int round_even(float x)
{
    MODEL_ASSUME(x >= -(ROUND_MAX + 0.5f) && x <= ROUND_MAX + 0.5f);
    int r = 0;
    if (x > 0.5f) r = 1;
    if (x >= 1.5f) r = 2;
    if (x > 2.5f) r = 3;
    if (x >= 3.5f) r = 4;
    if (x > 4.5f) r = 5;
    if (x >= 5.5f) r = 6;
    if (x > 6.5f) r = 7;
    if (x >= 7.5f) r = 8;
#if ROUND_MAX > 8
    if (x > 8.5f) r = 9;
    if (x >= 9.5f) r = 10;
    if (x > 10.5f) r = 11;
    if (x >= 11.5f) r = 12;
    if (x > 12.5f) r = 13;
    if (x >= 13.5f) r = 14;
    if (x > 14.5f) r = 15;
    if (x >= 15.5f) r = 16;
#endif
    if (x < -0.5f) r = -1;
    if (x <= -1.5f) r = -2;
    if (x < -2.5f) r = -3;
    if (x <= -3.5f) r = -4;
    if (x < -4.5f) r = -5;
    if (x <= -5.5f) r = -6;
    if (x < -6.5f) r = -7;
    if (x <= -7.5f) r = -8;
#if ROUND_MAX > 8
    if (x < -8.5f) r = -9;
    if (x <= -9.5f) r = -10;
    if (x < -10.5f) r = -11;
    if (x <= -11.5f) r = -12;
    if (x < -12.5f) r = -13;
    if (x <= -13.5f) r = -14;
    if (x < -14.5f) r = -15;
    if (x <= -15.5f) r = -16;
#endif
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
/* air (Grid.CheckRect clamps to the grid). room_col_t is 32 bits, or 64 for */
/* rooms taller than 32 tiles.                                               */
/* ------------------------------------------------------------------------ */
static int floor8(int v) { return v >> 3; } /* arithmetic shift == floor division by 8 */

static room_col_t col_bits(int c)
{
    if (c < 0 || c >= ROOM_W) return 0;
    return ROOM_COLS[c];
}

#ifdef MODEL_THREADS                 /* the beam search steps states on several threads */
#define MODEL_TLS _Thread_local
#else
#define MODEL_TLS
#endif

/* Zip movers are solids too: their boxes this frame, from zipTimer */
#if NZIPMOVERS > 0
static MODEL_TLS short CUR_ZIP_BOX[NZIPMOVERS][4];   /* x0, y0, x1, y1 (exclusive) */
static void load_zip_boxes(const State *s)
{
    for (int i = 0; i < NZIPMOVERS; i++) {
        int t = s->zipTimer[i];
        MODEL_ASSUME(t >= 0 && t <= ZIP_T_END);
        CUR_ZIP_BOX[i][0] = ZIP_POS[i][t][0];
        CUR_ZIP_BOX[i][1] = ZIP_POS[i][t][1];
        CUR_ZIP_BOX[i][2] = ZIP_POS[i][t][0] + ZIPMOVERS[i][2];
        CUR_ZIP_BOX[i][3] = ZIP_POS[i][t][1] + ZIPMOVERS[i][3];
    }
}
/* an 8 x h hitbox at (x, y) overlaps zip mover i */
static bool zip_overlap(int i, int x, int y, int h)
{
    return x + 4 > CUR_ZIP_BOX[i][0] && x - 4 < CUR_ZIP_BOX[i][2]
        && y > CUR_ZIP_BOX[i][1] && y - h < CUR_ZIP_BOX[i][3];
}
static bool zips_overlap(int x, int y, int h)
{
    for (int i = 0; i < NZIPMOVERS; i++)
        if (zip_overlap(i, x, y, h)) return true;
    return false;
}
#else
#define load_zip_boxes(s) ((void)0)
#define zips_overlap(x, y, h) false
#endif

#ifdef REFERENCE
/* bitmask of tile rows r0..r1 (inclusive), clipped to the grid */
static room_col_t row_span(int r0, int r1)
{
    const int BITS = (int)(8 * sizeof(room_col_t));
    if (r0 < 0) r0 = 0;
    if (r1 > ROOM_H - 1) r1 = ROOM_H - 1;
    if (r1 < r0) return 0;
    room_col_t upto = (r1 >= BITS - 1) ? (room_col_t)~(room_col_t)0 : (((room_col_t)1 << (r1 + 1)) - 1u);
    room_col_t below = ((room_col_t)1 << r0) - 1u;
    return upto & ~below;
}

/* hitbox 8 x h with offset (-4, -h), placed at (x, y) */
static bool collide_box(int x, int y, int h)
{
    room_col_t rows = row_span(floor8(y - h), floor8(y - 1));
    return ((col_bits(floor8(x - 4)) | col_bits(floor8(x + 3))) & rows) != 0 || zips_overlap(x, y, h);
}
#define LOAD_WINDOW(s) load_zip_boxes(s)
#else
/* Solver build: every collision check during one frame lies within a few
 * tiles of where the frame started (moves are <= 8 px, corner corrections
 * <= 4 px), so each frame first copies an 8x8-tile window of the room around
 * the player and all checks read that window instead of the whole room.
 * MODEL_ASSUME guards the bounds (the simulator asserts them). */
static MODEL_TLS int WX0, WY0;                 /* window origin, in tiles */
static MODEL_TLS unsigned char WCOL[8];        /* WCOL[i] bit j: tile (WX0+i, WY0+j) solid */

static void load_window(const State *s)
{
    WX0 = floor8(s->x - 28);
    WY0 = floor8(s->y - 32);
    for (int i = 0; i < 8; i++) {
#if ROOM_H <= 32
        unsigned long long c = (unsigned long long)col_bits(WX0 + i) << 8;  /* 8 rows of padding above */
        int sh = WY0 + 8;
        MODEL_ASSUME(sh >= 0 && sh < 56);
        WCOL[i] = (unsigned char)(c >> sh);
#else
        unsigned long long c = col_bits(WX0 + i);
        MODEL_ASSUME(WY0 >= -8 && WY0 < 64);
        WCOL[i] = (unsigned char)(WY0 < 0 ? c << (-WY0) : c >> WY0);
#endif
    }
    load_zip_boxes(s);
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
    return ((wcol(floor8(x - 4)) | wcol(floor8(x + 3))) & span8(r0, r1)) != 0 || zips_overlap(x, y, h);
}
#endif

static int collider_h(const State *s) { return s->ducking ? HB_DUCK_H : HB_NORMAL_H; }

/* CollideCheck<Solid>(at) with the current collider */
static bool collide_at(const State *s, int x, int y) { return collide_box(x, y, collider_h(s)); }

/* Scene.CollideCheck<Solid>(point) */
static bool solid_point(int px, int py)
{
#if NZIPMOVERS > 0
    for (int i = 0; i < NZIPMOVERS; i++) {
        if (px >= CUR_ZIP_BOX[i][0] && px < CUR_ZIP_BOX[i][2]
            && py >= CUR_ZIP_BOX[i][1] && py < CUR_ZIP_BOX[i][3])
            return true;
    }
#endif
#ifdef REFERENCE
    if (py < 0 || py >= ROOM_PX_H) return false;
    return (col_bits(floor8(px)) >> (py >> 3)) & 1ULL;
#else
    int r = floor8(py) - WY0;
    MODEL_ASSUME(r >= 0 && r < 8);
    return (wcol(floor8(px)) >> r) & 1u;
#endif
}


/* CollideCheck<Spikes>(at) with an 8 x h box: does it touch a spike strip
 * whose direction bit (1 << SPIKE_*) is in `mask`? */
static bool box_touches_spikes(int x, int y, int h, int mask)
{
#if NSPIKES > 0
    for (int i = 0; i < NPCOL; i++)
        if (PCOL[i][0] == PC_SPIKES && ((mask >> PCOL[i][1]) & 1) && x + 4 > PCOL[i][2] && x - 4 < PCOL[i][4]
            && y > PCOL[i][3] && y - h < PCOL[i][5])
            return true;
#else
    (void)x; (void)y; (void)h; (void)mask;
#endif
    return false;
}

/* Jump-through platforms: JumpThru hitbox W x 5 below the top edge. They only
 * stop downward moves, and only when Madeline is not already inside them
 * (CollideFirstOutside). */
#if NJUMPTHRUS > 0
static bool jt_overlap(int i, int x, int y, int h)
{
    return x + 4 > JUMPTHRUS[i][0] && x - 4 < JUMPTHRUS[i][2]
        && y > JUMPTHRUS[i][1] && y - h < JUMPTHRUS[i][1] + JUMPTHRU_H;
}
#endif

/* CollideCheckOutside<JumpThru>(at) for an 8 x h box that is now at (xn, yn) */
static bool jumpthru_outside(int h, int xn, int yn, int xa, int ya)
{
#if NJUMPTHRUS > 0
    for (int i = 0; i < NJUMPTHRUS; i++)
        if (jt_overlap(i, xa, ya, h) && !jt_overlap(i, xn, yn, h)) return true;
#else
    (void)h; (void)xn; (void)yn; (void)xa; (void)ya;
#endif
    return false;
}

/* CollideCheck<JumpThru>() at the current position */
static bool jumpthru_inside(const State *s)
{
#if NJUMPTHRUS > 0
    for (int i = 0; i < NJUMPTHRUS; i++)
        if (jt_overlap(i, s->x, s->y, collider_h(s))) return true;
#else
    (void)s;
#endif
    return false;
}

/* Actor.OnGround(at): a solid, or a jump-through entered from outside, 1 px below */
static bool on_ground_at(const State *s, int x, int y)
{
    return collide_at(s, x, y + 1) || jumpthru_outside(collider_h(s), x, y, x, y + 1);
}

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
        else if (dir > 0 && jumpthru_outside(collider_h(s), s->x, s->y, s->x, s->y + 1)) { hit = true; COV(C_JTLAND); }
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
    int stop = s->x + move;
    bool hit = false;
    if (move > 0) {
        int b = ((s->x + 4 + 7) >> 3) << 3;          /* first tile boundary at/after right edge */
        if (b < s->x + 4 + move && (wcol(b >> 3) & rows)) {
            stop = b - 4;
            hit = true;
        }
#if NZIPMOVERS > 0
        for (int i = 0; i < NZIPMOVERS; i++) {
            if (s->y > CUR_ZIP_BOX[i][1] && s->y - h < CUR_ZIP_BOX[i][3]) {
                int zx = CUR_ZIP_BOX[i][0];
                if (s->x + 4 <= zx && zx < s->x + 4 + move) {
                    if (!hit || zx - 4 < stop) {
                        stop = zx - 4;
                        hit = true;
                    }
                }
            }
        }
#endif
    } else {
        int a = ((s->x - 4) >> 3) << 3;              /* last tile boundary at/before left edge */
        if (s->x - 4 + move < a && (wcol((a >> 3) - 1) & rows)) {
            stop = a + 4;
            hit = true;
        }
#if NZIPMOVERS > 0
        for (int i = 0; i < NZIPMOVERS; i++) {
            if (s->y > CUR_ZIP_BOX[i][1] && s->y - h < CUR_ZIP_BOX[i][3]) {
                int zx = CUR_ZIP_BOX[i][2];
                if (s->x - 4 >= zx && zx > s->x - 4 + move) {
                    if (!hit || zx + 4 > stop) {
                        stop = zx + 4;
                        hit = true;
                    }
                }
            }
        }
#endif
    }
    s->x = stop;
    if (hit) s->remX = 0.0f;
    return hit;
}

static bool move_v_exact_plain(State *s, int move)
{
    MODEL_ASSUME(move >= -MAX_PIXELS_V && move <= MAX_PIXELS_V);
    if (move == 0) return false;
    int h = collider_h(s);
    unsigned cols = wcol(floor8(s->x - 4)) | wcol(floor8(s->x + 3));
    int stop = s->y + move;
    bool hit = false;
    if (move > 0) {
        int r = (s->y + 7) >> 3;                     /* first tile row at/below the feet */
        MODEL_ASSUME(r - WY0 >= 0 && r - WY0 < 8);
        if ((r << 3) < s->y + move && ((cols >> (r - WY0)) & 1u)) { stop = r << 3; hit = true; }
#if NJUMPTHRUS > 0
        /* a jump-through whose top the feet reach (from at/above it) stops her there */
        for (int i = 0; i < NJUMPTHRUS; i++) {
            int jy = JUMPTHRUS[i][1];
            if (s->x + 4 > JUMPTHRUS[i][0] && s->x - 4 < JUMPTHRUS[i][2] && jy >= s->y && jy < stop) {
                stop = jy;
                hit = true;
            }
        }
#endif
#if NZIPMOVERS > 0
        for (int i = 0; i < NZIPMOVERS; i++) {
            if (s->x + 4 > CUR_ZIP_BOX[i][0] && s->x - 4 < CUR_ZIP_BOX[i][2]) {
                int zy = CUR_ZIP_BOX[i][1];
                if (s->y <= zy && zy < stop) {
                    stop = zy;
                    hit = true;
                }
            }
        }
#endif
    } else {
        int a = ((s->y - h) >> 3) << 3;              /* last tile boundary at/above the head */
        int r = (a >> 3) - 1;
        MODEL_ASSUME(r - WY0 >= 0 && r - WY0 < 8);
        if (s->y - h + move < a && ((cols >> (r - WY0)) & 1u)) {
            stop = a + h;
            hit = true;
        }
#if NZIPMOVERS > 0
        for (int i = 0; i < NZIPMOVERS; i++) {
            if (s->x + 4 > CUR_ZIP_BOX[i][0] && s->x - 4 < CUR_ZIP_BOX[i][2]) {
                int zy = CUR_ZIP_BOX[i][3];
                if (s->y - h >= zy && zy + h > stop) {
                    stop = zy + h;
                    hit = true;
                }
            }
        }
#endif
    }
    s->y = stop;
    if (hit) s->remY = 0.0f;
    return hit;
}
#endif

/* Actor.MoveHExact / MoveVExact: whole pixels, stopping at the first solid.
 * With moving solids in the room, lift boosts allow moves beyond
 * MAX_PIXELS_*; they are done in pieces (the same pixel steps). */
static bool move_h_exact(State *s, int move)
{
#if NZIPMOVERS > 0
    bool hit = false;
    for (int i = 0; i < (ROUND_MAX + MAX_PIXELS_H - 1) / MAX_PIXELS_H && move != 0 && !hit; i++) {
        int step = move < -MAX_PIXELS_H ? -MAX_PIXELS_H : (move > MAX_PIXELS_H ? MAX_PIXELS_H : move);
        hit = move_h_exact_plain(s, step);
        move -= step;
    }
    return hit;
#else
    return move_h_exact_plain(s, move);
#endif
}

static bool move_v_exact(State *s, int move)
{
#if NZIPMOVERS > 0
    bool hit = false;
    for (int i = 0; i < (ROUND_MAX + MAX_PIXELS_V - 1) / MAX_PIXELS_V && move != 0 && !hit; i++) {
        int step = move < -MAX_PIXELS_V ? -MAX_PIXELS_V : (move > MAX_PIXELS_V ? MAX_PIXELS_V : move);
        hit = move_v_exact_plain(s, step);
        move -= step;
    }
    return hit;
#else
    return move_v_exact_plain(s, move);
#endif
}

/* Actor.MoveH / MoveV with the player's OnCollideH / OnCollideV callbacks.
 * (C# calls onCollide from inside the loop and returns right after, so
 * calling it after the loop is the same.) */
static void move_h(State *s, float amount)
{
    s->remX += amount;
    int move = round_even(s->remX);
    if (move == 0) return;
    s->remX -= (float)move;
    if (move_h_exact(s, move)) on_collide_h(s);
}

static void move_v(State *s, float amount)
{
    s->remY += amount;
    int move = round_even(s->remY);
    if (move == 0) return;
    s->remY -= (float)move;
    if (move_v_exact(s, move)) on_collide_v(s);
}

/* MoveV(float) with no callback (jump-through assist, springs) */
static void move_v_plain(State *s, float amount)
{
    s->remY += amount;
    int move = round_even(s->remY);
    if (move == 0) return;
    s->remY -= (float)move;
    move_v_exact(s, move);
}

/* MoveH(float) with no callback (used by duck correction) */
static void move_h_plain(State *s, float amount)
{
    s->remX += amount;
    int move = round_even(s->remX);
    if (move == 0) return;
    s->remX -= (float)move;
    move_h_exact(s, move);
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

static bool dash_attacking(const State *s) { return TPOS(s->dashAttackTimer); }
#define ALL_SPIKES ((1 << SPIKE_UP) | (1 << SPIKE_DOWN) | (1 << SPIKE_LEFT) | (1 << SPIKE_RIGHT))

/* WallJumpCheck. Since v1.2.3.0 a wall bounce (still dash-attacking after a
 * straight-up dash) reaches 5 px instead of 3 -- unless spikes facing her
 * are within those 5 px. */
static bool wall_jump_check(const State *s, int dir)
{
    int dist = WALL_JUMP_CHECK_DIST;
    if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1
        && !box_touches_spikes(s->x + dir * WALL_BOUNCE_CHECK_DIST, s->y, collider_h(s),
                               1 << (dir <= 0 ? SPIKE_RIGHT : SPIKE_LEFT)))
        dist = WALL_BOUNCE_CHECK_DIST;
    return climb_bounds_check(s, dir) && collide_at(s, s->x + dir * dist, s->y);
}

/* DashCorrectCheck (v1.4): would her hurtbox (8 x 9, 2 px above her feet),
 * moved by (ax, ay), touch spikes? Dash corner corrections, the dash
 * jump-through nudge and the dash floor snap are skipped then. */
static bool dash_correct_check(const State *s, int ax, int ay)
{
    return box_touches_spikes(s->x + ax, s->y + ay - 2, 9, ALL_SPIKES);
}

/* a solid within 3 px to either side, also after the dash jump-through
 * nudge (up to 6 px up) that DashUpdate does before its wall checks */
static bool wall_within_3(const State *s)
{
    return collide_box(s->x - 3, s->y, HB_NORMAL_H + DASH_H_JUMPTHRU_NUDGE)
        || collide_box(s->x + 3, s->y, HB_NORMAL_H + DASH_H_JUMPTHRU_NUDGE);
}

static bool grab_near_wall(const State *s)
{
    return wall_within_3(s)
        || collide_box(s->x - 2, s->y - 2, HB_NORMAL_H) || collide_box(s->x + 2, s->y - 2, HB_NORMAL_H)
        || collide_box(s->x - WALL_BOUNCE_CHECK_DIST, s->y, HB_NORMAL_H)
        || collide_box(s->x + WALL_BOUNCE_CHECK_DIST, s->y, HB_NORMAL_H);
}

/* Can holding Grab change anything this frame? In the normal state,
 * climbing starts need a solid 2 px to the side (at most 2 px higher), grab
 * wall slides one 1 px to the side, climb jumps one 3 px to the side (5 px
 * after a straight-up dash). With the player's own box free, all of these
 * touch one of the boxes in grab_near_wall (the beam search's cheap test).
 * In the dash state Grab is read for a climb jump out of the dash (a jump
 * press with a wall 3 px to the side, possibly after the jump-through nudge)
 * and for holdables (not modelled). Used to prune the search; it never
 * changes the outcome. Must be called after this frame's button update (it
 * reads the jump press). */
static bool jump_pressed(const State *s);
static bool grab_can_matter(const State *s)
{
    if (s->state == ST_CLIMB) return true;
    if (s->state == ST_DASH)
        return jump_pressed(s) && wall_within_3(s);
    /* after a straight-up dash WallJumpCheck (and so a climb jump) reaches 5 px */
    if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1
        && (collide_box(s->x - WALL_BOUNCE_CHECK_DIST, s->y, HB_NORMAL_H) || collide_box(s->x + WALL_BOUNCE_CHECK_DIST, s->y, HB_NORMAL_H)))
        return true;
    return grab_near_wall(s);
}

static bool jump_pressed(const State *s) { return TPOS(s->jumpBuf) || s->jumpEdge; }
static bool dash_pressed(const State *s) { return TPOS(s->dashBuf) || s->dashEdge; }
static bool cdash_pressed(const State *s) { return TPOS(s->cdashBuf) || s->cdashEdge; }
/* CanDash: (Input.CrouchDashPressed || Input.DashPressed) && cooldown over && dashes left */
static bool can_dash(const State *s)
{
    return (dash_pressed(s) || cdash_pressed(s)) && !TPOS(s->dashCooldownTimer) && s->dashes > 0;
}

/* ------------------------------------------------------------------------ */
/* Lift speed (moving solids)                                               */
/* ------------------------------------------------------------------------ */
#if NZIPMOVERS > 0
/* Actor.LiftSpeed getter: currentLiftSpeed, or while it is zero the last
 * non-zero one (kept for LiftSpeedGraceTime) */
static bool lift_current(const State *s) { return s->liftSpeedX != 0.0f || s->liftSpeedY != 0.0f; }
static float lift_x(const State *s) { return lift_current(s) ? s->liftSpeedX : s->liftLastX; }
static float lift_y(const State *s) { return lift_current(s) ? s->liftSpeedY : s->liftLastY; }

/* Actor.LiftSpeed setter */
static void set_lift(State *s, float x, float y)
{
    s->liftSpeedX = x;
    s->liftSpeedY = y;
    if (x != 0.0f || y != 0.0f) {
        s->liftLastX = x;
        s->liftLastY = y;
        TSET(s->liftGraceTimer, LIFT_SPEED_GRACE_TIME);
    }
}

/* Player.LiftBoost: LiftSpeed with |x| capped at LiftXCap, y in [LiftYCap, 0] */
static float lift_boost_x(const State *s)
{
    float vx = lift_x(s);
    if (vx > LIFT_X_CAP) return LIFT_X_CAP;
    if (vx < -LIFT_X_CAP) return -LIFT_X_CAP;
    return vx;
}
static float lift_boost_y(const State *s)
{
    float vy = lift_y(s);
    if (vy > 0.0f) return 0.0f;
    if (vy < LIFT_Y_CAP) return LIFT_Y_CAP;
    return vy;
}
/* Speed += LiftBoost */
#define ADD_LIFT_BOOST(s) do { (s)->spdX += lift_boost_x(s); (s)->spdY += lift_boost_y(s); } while (0)

/* Actor.Update, after the state machine: LiftSpeed = Vector2.Zero, and the
 * grace timer runs down (lastLiftSpeed is forgotten when it ends) */
static void actor_update_lift(State *s)
{
    s->liftSpeedX = 0.0f;
    s->liftSpeedY = 0.0f;
    if (TPOS(s->liftGraceTimer)) {
        TDEC(s->liftGraceTimer);
        if (!TPOS(s->liftGraceTimer)) { s->liftLastX = 0.0f; s->liftLastY = 0.0f; }
    }
}
#else
#define ADD_LIFT_BOOST(s) ((void)0)
#define actor_update_lift(s) ((void)0)
#endif

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
    TCLR(s->wallBoostTimer);
    /* Speed.X += JumpHBoost * moveX */
    s->spdX += (s->moveX > 0 ? JUMP_H_BOOST * 1.0f : (s->moveX < 0 ? JUMP_H_BOOST * -1.0f : JUMP_H_BOOST * 0.0f));
    s->spdY = JUMP_SPEED;
    ADD_LIFT_BOOST(s);
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
    TCLR(s->wallBoostTimer);
#if NZIPMOVERS > 0
    s->spdX = s->facing > 0 ? SUPER_JUMP_H : -SUPER_JUMP_H;
    s->spdY = JUMP_SPEED;
    ADD_LIFT_BOOST(s);
    if (s->ducking) {                     /* hyper */
        COV(C_HYPER);
        s->ducking = false;
        s->spdX *= DUCK_SUPER_JUMP_X_MULT;
        s->spdY *= DUCK_SUPER_JUMP_Y_MULT;
    }
#else                                     /* the same products, folded */
    s->spdX = s->facing > 0 ? SUPER_JUMP_H : -SUPER_JUMP_H;
    s->spdY = JUMP_SPEED;
    if (s->ducking) {                     /* hyper */
        COV(C_HYPER);
        s->ducking = false;
        s->spdX = s->facing > 0 ? SUPER_JUMP_H * DUCK_SUPER_JUMP_X_MULT
                                : (-SUPER_JUMP_H) * DUCK_SUPER_JUMP_X_MULT;
        s->spdY = JUMP_SPEED * DUCK_SUPER_JUMP_Y_MULT;
    }
#endif
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
    TCLR(s->wallBoostTimer);
    if (s->moveX != 0) {
        s->forceMoveX = dir;
        TSET(s->forceMoveXTimer, WALL_JUMP_FORCE_TIME);
    }
#if NZIPMOVERS > 0 && defined(ZIP_WALL_LIFT)
    /* Get lift of wall jumped off of: if (LiftSpeed == Vector2.Zero) the
     * LiftSpeed of the solid 3 px to her right (Player.cs checks +3 px
     * whatever the direction). Off by default: a zip mover moves inside its
     * coroutine, and Platform.Update zeroes LiftSpeed right after (so this
     * reads zero) -- a guess to be settled by a recording. */
    if (!lift_current(s))
        for (int i = 0; i < NZIPMOVERS; i++)
            if (zip_overlap(i, s->x + WALL_JUMP_CHECK_DIST, s->y, collider_h(s))) {
                set_lift(s, ZIP_LIFT[i][s->zipTimer[i]][0], ZIP_LIFT[i][s->zipTimer[i]][1]);
                break;
            }
#endif
    s->spdX = dir > 0 ? WALL_JUMP_H_SPEED : -WALL_JUMP_H_SPEED;
    s->spdY = JUMP_SPEED;
    ADD_LIFT_BOOST(s);
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
    TCLR(s->wallBoostTimer);
    s->spdX = dir > 0 ? SUPER_WALL_JUMP_H : -SUPER_WALL_JUMP_H;
    s->spdY = SUPER_WALL_JUMP_SPEED;
    ADD_LIFT_BOOST(s);
    s->varJumpSpeed = s->spdY;
}

static void climb_jump(State *s)
{
    COV(C_CLIMBJUMP);
    if (!s->onGround) s->stamina -= CLIMB_JUMP_COST;
    jump(s);                                      /* Jump(false, false) */
    if (s->moveX == 0) {
        s->wallBoostDir = -s->facing;
        TSET(s->wallBoostTimer, CLIMB_JUMP_BOOST_TIME);
    }
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
            /* for i in 1..4, j in {+1,-1}: at = Position + (sx, i*j) free,
             * at - (0, j) solid, and (v1.4) no spikes there for her hurtbox */
            int dy = 0;
            for (int i = 1; i <= DASH_CORNER_CORRECTION && dy == 0; i++)
                for (int j = 1; j >= -1 && dy == 0; j -= 2)
                    if (!collide_at(s, s->x + sx, s->y + i * j) && collide_at(s, s->x + sx, s->y + i * j - j)
                        && !dash_correct_check(s, sx, i * j))
                        dy = i * j;
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
                    if (!on_ground_at(s, s->x - i, s->y)) dx = -i;
                }
            }
            if (dx == 0 && s->spdX >= 0) {
                for (int i = 1; i <= DASH_CORNER_CORRECTION; i++) {
                    if (dx != 0) break;
                    if (!on_ground_at(s, s->x + i, s->y)) dx = i;
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
            /* upward corner correction: 4 px, 5 px while dash-attacking
             * straight up (v1.2.3.0); left first when Speed.X <= 0.01,
             * then right when Speed.X >= -0.01 */
            int dx = 0;
            int reach = dash_attacking(s) && absf(s->spdX) < 0.01f ? UPWARD_CORNER_CORRECTION_DASH
                                                                    : UPWARD_CORNER_CORRECTION;
            if (s->spdX <= 0.01f) {
                for (int i = 1; i <= UPWARD_CORNER_CORRECTION_DASH; i++) {
                    if (dx != 0 || i > reach) break;
                    if (!collide_at(s, s->x - i, s->y - 1)) dx = -i;
                }
            }
            if (dx == 0 && s->spdX >= -0.01f) {
                for (int i = 1; i <= UPWARD_CORNER_CORRECTION_DASH; i++) {
                    if (dx != 0 || i > reach) break;
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
static void normal_end(State *s)
{
    TCLR(s->wallBoostTimer);
    TCLR(s->wallSpeedRetentionTimer);
    s->hopWaitX = 0;
}

static void climb_begin(State *s)
{
    COV(C_CLIMB);
    s->autoJump = false;
    s->spdX = 0;
    s->spdY *= CLIMB_GRAB_Y_MULT;
    WS_SET(s);
    TSET(s->climbNoMoveTimer, CLIMB_NO_MOVE_TIME);
    TCLR(s->wallBoostTimer);
    s->lastClimbMove = 0;
    /* snap to the wall: up to ClimbCheckDist pixels (Position += UnitX * Facing) */
    for (int i = 0; i < CLIMB_CHECK_DIST; i++) {
        if (collide_at(s, s->x + s->facing, s->y)) break;
        s->x += s->facing;
    }
}

static void climb_end(State *s) { TCLR(s->wallSpeedRetentionTimer); }

static void dash_begin(State *s, int moveY)
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
    else if (!s->ducking && (s->demoDashed || moveY == 1)) {   /* crouch dash, or Down held */
        COV(C_CROUCHDASH);
        s->ducking = true;
    }
    s->demoDashed = false;                                    /* (only read here) */
}

/* moveY: Input.MoveY on this frame (read by DashBegin) */
static void set_state(State *s, int next, int moveY)
{
    if (s->state == next) return;
    int prev = s->state;
    s->state = next;
    if (prev == ST_NORMAL) normal_end(s);
    else if (prev == ST_CLIMB) climb_end(s);     /* DashEnd only fires dash events */
    if (next == ST_NORMAL) normal_begin(s);
    else if (next == ST_CLIMB) climb_begin(s);
    else dash_begin(s, moveY);
    if (next == ST_DASH) {
        s->coActive = true;                      /* currentCoroutine.Replace(DashCoroutine()) */
        s->coStage = 0;
    } else {
        s->coActive = false;                     /* currentCoroutine.Cancel() */
    }
    TCLR(s->coWait);
}

static int start_dash(State *s)
{
    s->dashes = s->dashes - 1 > 0 ? s->dashes - 1 : 0;
    s->demoDashed = cdash_pressed(s);            /* demoDashed = Input.CrouchDashPressed */
    TCLR(s->dashBuf);                            /* Input.Dash.ConsumeBuffer() */
    TCLR(s->cdashBuf);                           /* Input.CrouchDash.ConsumeBuffer() */
    return ST_DASH;
}

static bool climb_check(const State *s, int dir, int yAdd)
{
    return climb_bounds_check(s, dir) && collide_at(s, s->x + dir * CLIMB_CHECK_DIST, s->y + yAdd);
}

/* IsTired: CheckStamina < ClimbTiredThreshold */
static bool is_tired(const State *s)
{
    float check = TPOS(s->wallBoostTimer) ? s->stamina + CLIMB_JUMP_COST : s->stamina;
    return check < CLIMB_TIRED_THRESHOLD;
}

static int normal_update(State *s, Input in, bool wasOnGround)
{
#if NZIPMOVERS > 0
    /* Use Lift Boost if walked off platform */
    if (lift_boost_y(s) < 0 && wasOnGround && !s->onGround && s->spdY >= 0)
        s->spdY = lift_boost_y(s);
#else
    (void)wasOnGround;
#endif
    /* (no holdables, wind or climb blockers) */

    /* Climbing */
    if (in.grab && !is_tired(s) && !s->ducking) {
        if (s->spdY >= 0 && signf(s->spdX) != -s->facing) {
            if (climb_check(s, s->facing, 0)) {
                s->ducking = false;
                return ST_CLIMB;
            }
            if (in.my < 1) {
                for (int i = 1; i <= CLIMB_UP_CHECK_DIST; i++) {
                    if (!collide_at(s, s->x, s->y - i) && climb_check(s, s->facing, -i)) {
                        move_v_exact_plain(s, -i);
                        s->ducking = false;
                        return ST_CLIMB;
                    }
                }
            }
        }
    }

    /* Dashing */
    if (can_dash(s)) {
        ADD_LIFT_BOOST(s);
        return start_dash(s);
    }

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

        /* wall slide */
        if ((s->moveX == s->facing || (s->moveX == 0 && in.grab)) && in.my != 1) {
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
                if (s->facing > 0 && in.grab && s->stamina > 0)
                    climb_jump(s);
                else if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1)
                    super_wall_jump(s, -1);
                else
                    wall_jump(s, -1);
            } else if (wall_jump_check(s, -1)) {
                if (s->facing < 0 && in.grab && s->stamina > 0)
                    climb_jump(s);
                else if (dash_attacking(s) && s->dashDirX == 0 && s->dashDirY == -1)
                    super_wall_jump(s, 1);
                else
                    wall_jump(s, 1);
            }
        }
    }

    return ST_NORMAL;
}

static int dash_update(State *s, Input in)
{
    if (s->dashDirY == 0) {
        /* JumpThru correction: dashing sideways with the feet just inside a
         * jump-through (up to 6 px) puts her on top of it */
#if NJUMPTHRUS > 0
        for (int i = 0; i < NJUMPTHRUS; i++)
            if (jt_overlap(i, s->x, s->y, collider_h(s)) && s->y - JUMPTHRUS[i][1] <= DASH_H_JUMPTHRU_NUDGE
                && !dash_correct_check(s, 0, JUMPTHRUS[i][1] - s->y)) {            /* v1.4: not onto spikes */
                COV(C_JTNUDGE);
                move_v_exact_plain(s, JUMPTHRUS[i][1] - s->y);
            }
#endif
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
        /* Since v1.2.2.4 a jump at a wall while holding Grab and facing it
         * is a climb jump, as in the normal state (changelog: "You can now
         * perform a climb jump from the Dash state"). */
        if (jump_pressed(s) && can_unduck(s)) {
            if (wall_jump_check(s, 1)) {
                if (s->facing > 0 && in.grab && s->stamina > 0) { COV(C_DASHCLIMBJUMP); climb_jump(s); }
                else wall_jump(s, -1);
                return ST_NORMAL;
            } else if (wall_jump_check(s, -1)) {
                if (s->facing < 0 && in.grab && s->stamina > 0) { COV(C_DASHCLIMBJUMP); climb_jump(s); }
                else wall_jump(s, 1);
                return ST_NORMAL;
            }
        }
    }

    return ST_DASH;
}

/* SlipCheck: are Madeline's hands above the top of the wall? Two points
 * beside the top of the hitbox; addY is (as in the game) applied twice to
 * the upper point. */
static bool slip_check(const State *s, int addY)
{
    int h = collider_h(s);
    int ax = s->facing > 0 ? s->x + 4 : s->x - 5;   /* TopRight, or TopLeft - UnitX */
    int ay = s->y - h + 4 + addY;
    return !solid_point(ax, ay) && !solid_point(ax, ay - 4 + addY);
}

/* ClimbHopBlockedCheck: spikes (their LedgeBlocker) where the hop would
 * land, or a solid 6 px above */
static bool climb_hop_blocked_check(const State *s)
{
    if (box_touches_spikes(s->x + s->facing * 8, s->y, collider_h(s),
                           (1 << SPIKE_UP) | (1 << SPIKE_LEFT) | (1 << SPIKE_RIGHT))) {
        COV(C_HOPBLOCKED);
        return true;
    }
    return collide_at(s, s->x, s->y - 6);
}

static void climb_hop(State *s)
{
    COV(C_CLIMBHOP);
    if (collide_at(s, s->x + s->facing, s->y)) {   /* climbHopSolid != null: wait until clear */
        s->hopWaitX = s->facing;
    } else {
        s->hopWaitX = 0;
        s->spdX = s->facing > 0 ? CLIMB_HOP_X : -CLIMB_HOP_X;
    }
    s->spdY = minf(s->spdY, CLIMB_HOP_Y);
    s->forceMoveX = 0;
    TSET(s->forceMoveXTimer, CLIMB_HOP_FORCE_TIME);
}

static int climb_update(State *s, Input in)
{
    TDEC_FREE(s->climbNoMoveTimer);
    bool noMove = TPOS(s->climbNoMoveTimer);   /* climbNoMoveTimer > 0 */

    /* Refill stamina on ground */
    if (s->onGround) s->stamina = CLIMB_MAX_STAMINA;

    /* Wall jump */
    if (jump_pressed(s) && (!s->ducking || can_unduck(s))) {
        if (s->moveX == -s->facing) wall_jump(s, -s->facing);
        else climb_jump(s);
        return ST_NORMAL;
    }

    /* Dashing */
    if (can_dash(s)) {
        ADD_LIFT_BOOST(s);
        return start_dash(s);
    }

    /* Let go */
    if (!in.grab) {
        ADD_LIFT_BOOST(s);
        return ST_NORMAL;
    }

    /* No wall to hold */
    if (!collide_at(s, s->x + s->facing, s->y)) {
        if (s->spdY < 0) climb_hop(s);           /* climbed over the ledge */
        return ST_NORMAL;
    }

    /* Climbing (no wall boosters or climb blockers) */
    float target = 0.0f;
    bool trySlip = false;
    if (!noMove) {
        if (in.my == -1) {
            target = CLIMB_UP_SPEED;
            /* up limit */
            if (collide_at(s, s->x, s->y - 1) || (climb_hop_blocked_check(s) && slip_check(s, -1))) {
                if (s->spdY < 0) s->spdY = 0;
                target = 0.0f;
                trySlip = true;
            } else if (slip_check(s, 0)) {
                climb_hop(s);                    /* hopping */
                return ST_NORMAL;
            }
        } else if (in.my == 1) {
            target = CLIMB_DOWN_SPEED;
            if (s->onGround) {
                if (s->spdY > 0) s->spdY = 0;
                target = 0.0f;
            }
        } else {
            trySlip = true;
        }
    } else {
        trySlip = true;
    }
    s->lastClimbMove = target < 0 ? -1 : (target > 0 ? 1 : 0);   /* Math.Sign(target) */
    if (s->lastClimbMove < 0) COV(C_CLIMBUP);
    if (s->lastClimbMove > 0) COV(C_CLIMBDOWN);

    /* slip down if the hands are above the ledge and there is no vertical input */
    if (trySlip && slip_check(s, 0)) {
        COV(C_SLIP);
        target = CLIMB_SLIP_SPEED;
    }
    s->spdY = approach(s->spdY, target, CLIMB_ACCEL * DT);

    /* down limit */
    if (in.my != 1 && s->spdY > 0 && !collide_at(s, s->x + s->facing, s->y + 1)) s->spdY = 0;

    /* stamina */
    if (!noMove) {
        if (s->lastClimbMove == -1) s->stamina -= CLIMB_UP_COST * DT;
        else if (s->lastClimbMove == 0) s->stamina -= CLIMB_STILL_COST * DT;
    }

    /* too tired */
    if (s->stamina <= 0) {
        COV(C_TIRED);
        ADD_LIFT_BOOST(s);
        return ST_NORMAL;
    }
    return ST_CLIMB;
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
    set_state(s, ST_NORMAL, 0);
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
/* Player colliders (Spikes, Spring) and room bounds (Level.EnforceBounds)  */
/* ------------------------------------------------------------------------ */
/* Spring.OnCollide -> Player.SuperBounce(spring top): back on top of the
 * spring, dash and stamina refilled, Speed = (0, -185) with 0.2 s of
 * automatic variable jump. (The game switches to the normal state before
 * setting the timers; NormalBegin only resets maxFall, so the order here
 * gives the same result.) */
static void super_bounce(State *s, int fromY)
{
    COV(C_SPRING);
    bool duck = s->ducking;
    s->ducking = false;                          /* Collider = normalHitbox for the move */
    /* MoveV(fromY - Bottom), no callback. The distance k is a whole number of
     * pixels, up to 16 when she touches the side of a spring from below its
     * base. movementCounter.Y += k rounds like the game; the solver build then
     * rounds the sum without a general float->int conversion: sum - k is
     * exact and within +-0.5, and a tie goes to the even neighbour. */
    int k = fromY - s->y;
    s->remY += (float)k;
#ifdef REFERENCE
    int move = round_even(s->remY);
#else
    float d = s->remY - (float)k;
    int move = k;
    if (d == 0.5f && (k & 1)) move = k + 1;
    if (d == -0.5f && (k & 1)) move = k - 1;
#endif
    if (move != 0) {
        s->remY -= (float)move;
        /* MoveVExact in steps of at most 6 px; |move| <= 18, so 3 steps do
         * (a fixed bound, so CBMC unrolls the loop finitely) */
        bool hit = false;
        for (int i = 0; i < 3 && move != 0 && !hit; i++) {
            int step = move < -MAX_PIXELS_V ? -MAX_PIXELS_V : (move > MAX_PIXELS_V ? MAX_PIXELS_V : move);
            hit = move_v_exact_plain(s, step);
            if (!hit) move -= step;
        }
        MODEL_ASSUME(hit || move == 0);
    }
    s->ducking = duck;                           /* Collider = was */
    if (s->dashes < MAX_DASHES) s->dashes = MAX_DASHES;
    s->stamina = CLIMB_MAX_STAMINA;
    TCLR(s->jumpGraceTimer);
    TSET(s->varJumpTimer, SUPER_BOUNCE_VAR_JUMP_TIME);
    s->varJumpLong = false;
    s->autoJump = true;
    TCLR(s->dashAttackTimer);
    WS_SET(s);
    TCLR(s->wallBoostTimer);
    s->spdX = 0;
    s->spdY = SUPER_BOUNCE_SPEED;
    s->varJumpSpeed = s->spdY;
    set_state(s, ST_NORMAL, 0);
}

/* The PlayerCollider loop of Player.Update, with the hurtbox (8x9 at (-4,-11),
 * ducking 8x4 at (-4,-6)), in the order the entities were placed.
 *   spikes (a 3 px strip [x0,x1) x [y0,y1)): up spikes kill when falling or
 *     standing (Speed.Y >= 0) with the hurtbox bottom not below the spike
 *     base, down spikes when Speed.Y <= 0, left spikes when Speed.X >= 0,
 *     right spikes when Speed.X <= 0;
 *   floor springs (16x6 above their base): bounce when Speed.Y >= 0. */
static void player_colliders(State *s)
{
#if NPCOL > 0
    for (int i = 0; i < NPCOL; i++) {
        int hl = s->x - 4, hr = s->x + 4;
        int ht = s->y - (s->ducking ? 6 : 11), hb = s->y - 2;
        if (PCOL[i][0] == PC_SPIKES) {
            if (hr > PCOL[i][2] && hl < PCOL[i][4] && hb > PCOL[i][3] && ht < PCOL[i][5]) {
                int d = PCOL[i][1];
                bool kill = false;
                if (d == SPIKE_UP    && s->spdY >= 0 && hb <= PCOL[i][5]) { COV(C_SPIKE_U); kill = true; }
                if (d == SPIKE_DOWN  && s->spdY <= 0) { COV(C_SPIKE_D); kill = true; }
                if (d == SPIKE_LEFT  && s->spdX >= 0) { COV(C_SPIKE_L); kill = true; }
                if (d == SPIKE_RIGHT && s->spdX <= 0) { COV(C_SPIKE_R); kill = true; }
                if (kill) { s->dead = true; return; }
            }
        } else {
            int sx = PCOL[i][1], sy = PCOL[i][2];
            if (hr > sx - 8 && hl < sx + 8 && hb > sy - 6 && ht < sy && s->spdY >= 0)
                super_bounce(s, sy - 6);
        }
    }
#else
    (void)s;
#endif
}

/* MapData.CanTransitionTo(point just outside `side`): is there a neighbouring
 * room there? EXITS[i] = { side, from, to, goal } in room pixels along that
 * edge. v2 is twice the coordinate along the edge (Collider.CenterY can end
 * in .5), so everything stays integer. Returns 0 (no room), 1 (the goal) or
 * 2 (another room). */
static int neighbour(int side, int v2)
{
    for (int i = 0; i < NEXITS; i++)
        if (EXITS[i][0] == side && v2 >= 2 * EXITS[i][1] && v2 < 2 * EXITS[i][2]) return EXITS[i][3] ? 1 : 2;
    return 0;
}

/* level transition: into the goal room, or into another one (a failed run) */
static void leave_room(State *s, int n)
{
    if (n == 1) s->exited = true;
    else { COV(C_LEAVE); s->dead = true; }
}

/* Level.EnforceBounds. Horizontal transitions test the point
 * Center + (+-8, 0), vertical ones Center + (0, +-12); only the coordinate
 * along the edge matters for which neighbour is hit. */
static void enforce_bounds(State *s)
{
    int h = collider_h(s);
    int cy2 = 2 * s->y - h;                                   /* 2 * Collider.CenterY = 2 * (Top + h / 2) */

    if (s->x - 4 < 0) {
        int n = (s->y - h >= 0 && s->y < ROOM_PX_H) ? neighbour(EXIT_SIDE_LEFT, cy2) : 0;
        if (n) { if (n == 1) COV(C_EXIT_L); leave_room(s, n); return; }
        s->x = 4;                                             /* player.Left = bounds.Left */
        s->spdX = 0;                                          /* OnBoundsH */
    } else if (s->x + 4 > ROOM_PX_W) {
        int n = (s->y - h >= 0 && s->y < ROOM_PX_H) ? neighbour(EXIT_SIDE_RIGHT, cy2) : 0;
        if (n) { if (n == 1) COV(C_EXIT_R); leave_room(s, n); return; }
        s->x = ROOM_PX_W - 4;
        s->spdX = 0;
    }

    if (cy2 < 0) {                                            /* CenterY < bounds.Top */
        int n = neighbour(EXIT_SIDE_UP, 2 * s->x);
        if (n) { if (n == 1) COV(C_EXIT_U); leave_room(s, n); return; }
        if (s->y - h < -24) {                                 /* player.Top = bounds.Top - 24 */
            COV(C_TOPCLAMP);
            s->y = -24 + h;
            s->spdY = 0;                                      /* OnBoundsV */
        }
    } else if (s->y > ROOM_PX_H && neighbour(EXIT_SIDE_DOWN, 2 * s->x)) {
        if (!collide_at(s, s->x, s->y + 4)) {
            int n = neighbour(EXIT_SIDE_DOWN, 2 * s->x);
            if (n == 1) COV(C_EXIT_D);
            leave_room(s, n);
            return;
        }
    } else if (s->y - h > ROOM_PX_H + 4) {
        COV(C_FELL);
        s->dead = true;                                       /* fell out of the level */
    }
}

/* ------------------------------------------------------------------------ */
/* Player.Update                                                            */
/* ------------------------------------------------------------------------ */
static void player_update(State *s, Input in)
{
    LOAD_WINDOW(s);
    FRAME_HOOK(s, in);

    /* Get ground (a solid, or a jump-through from above) */
    bool wasOnGround = s->onGround;               /* set at the end of the last Player.Update */
    if (s->spdY >= 0) s->onGround = on_ground_at(s, s->x, s->y);
    else s->onGround = false;

    /* Wall slide */
    if (s->wallSlideDir != 0) {
        WS_DEC(s);
        s->wallSlideDir = 0;
    }

    /* Wall boost (uses last frame's moveX: moveX is read below) */
    if (TPOS(s->wallBoostTimer)) {
        TDEC(s->wallBoostTimer);
        if (s->moveX == s->wallBoostDir) {
            COV(C_WALLBOOST);
            s->spdX = s->moveX > 0 ? WALL_JUMP_H_SPEED : -WALL_JUMP_H_SPEED;   /* WallJumpHSpeed * moveX */
            s->stamina += CLIMB_JUMP_COST;
            TCLR(s->wallBoostTimer);
        }
    }

    /* After dash */
    if (s->onGround && s->state != ST_CLIMB) {
        s->autoJump = false;
        s->stamina = CLIMB_MAX_STAMINA;
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
    else if (s->onGround && s->dashes < MAX_DASHES) {
        if (!box_touches_spikes(s->x, s->y, collider_h(s), 15)) s->dashes = MAX_DASHES;
        else COV(C_NOSPIKEREFILL);
    }

    /* Var jump */
    if (TPOS(s->varJumpTimer)) TDEC(s->varJumpTimer);

    /* Force move X */
    if (TPOS(s->forceMoveXTimer)) {
        TDEC(s->forceMoveXTimer);
        s->moveX = s->forceMoveX;
    } else {
        s->moveX = in.mx;
    }

    /* Facing (not while climbing) */
    if (s->moveX != 0 && s->state != ST_CLIMB) s->facing = s->moveX;

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

    /* Hop wait X (after a climb hop, until the wall is out of the way) */
    if (s->hopWaitX != 0) {
        if (signf(s->spdX) == -s->hopWaitX || s->spdY > 0) {
            s->hopWaitX = 0;
        } else if (!collide_at(s, s->x + s->hopWaitX, s->y)) {
            COV(C_HOPWAIT);
            s->spdX = s->hopWaitX > 0 ? CLIMB_HOP_X : -CLIMB_HOP_X;
            s->hopWaitX = 0;
        }
    }

    /* base.Update() -> StateMachine.Update() */
    int next = s->state == ST_NORMAL ? normal_update(s, in, wasOnGround)
             : s->state == ST_CLIMB  ? climb_update(s, in)
             : dash_update(s, in);
    set_state(s, next, in.my);
    if (s->coActive) coroutine_update(s);
    actor_update_lift(s);                         /* rest of Actor.Update */

    /* Jump-through assist: rising inside a jump-through nudges her up
     * (unless spikes would block the hop) */
    if (!s->onGround && s->spdY <= 0 && (s->state != ST_CLIMB || s->lastClimbMove == -1)
        && jumpthru_inside(s)
        && !box_touches_spikes(s->x, s->y - 2, collider_h(s), (1 << SPIKE_UP) | (1 << SPIKE_LEFT) | (1 << SPIKE_RIGHT))) {
        COV(C_JTASSIST);
        move_v_plain(s, JUMPTHRU_ASSIST_SPEED * DT);
    }

    /* Dash floor snapping */
    if (!s->onGround && dash_attacking(s) && s->dashDirY == 0) {
        bool jt = jumpthru_outside(collider_h(s), s->x, s->y, s->x, s->y + DASH_V_FLOOR_SNAP_DIST);
        if ((collide_at(s, s->x, s->y + DASH_V_FLOOR_SNAP_DIST) || jt)
            && !dash_correct_check(s, 0, DASH_V_FLOOR_SNAP_DIST)) {                /* v1.4: not onto spikes */
            COV(C_FLOORSNAP);
            if (jt) COV(C_JTSNAP);
            move_v_exact_plain(s, DASH_V_FLOOR_SNAP_DIST);
        }
    }

    /* Falling unducking */
    if (s->spdY > 0 && can_unduck(s) && !s->onGround) s->ducking = false;

    /* Physics */
    move_h(s, s->spdX * DT);
    move_v(s, s->spdY * DT);

    /* Player colliders (spikes, springs), then the room bounds */
    player_colliders(s);
    if (s->dead) return;

    /* Level.EnforceBounds */
    enforce_bounds(s);
}

#if NZIPMOVERS > 0
/* ------------------------------------------------------------------------ */
/* Zip movers (ZipMover : Solid)                                            */
/* ------------------------------------------------------------------------ */
/* Once the level is loaded, the player's entity comes before the room's
 * entities (she is carried over from the previous room), so every frame the
 * zip movers update after her: they see where her update left her, and she
 * sees their LiftSpeed on the next frame. (A room loaded from scratch adds
 * her after its entities; that order is not modelled.) */

/* Player.IsRiding(Solid): climbing, the solid 1 px in front of her; otherwise
 * Actor.IsRiding: standing on it (1 px below) */
static bool riding_zip(const State *s, int i)
{
    if (s->state == ST_CLIMB) return zip_overlap(i, s->x + s->facing, s->y, collider_h(s));
    return zip_overlap(i, s->x, s->y + 1, collider_h(s));
}

static void zip_shift(int i, int dx, int dy)
{
    CUR_ZIP_BOX[i][0] += dx; CUR_ZIP_BOX[i][2] += dx;
    CUR_ZIP_BOX[i][1] += dy; CUR_ZIP_BOX[i][3] += dy;
}

/* squished: Player.OnSquish ducks or wiggles out when it can (not modelled) */
#define SQUISH(s) do { COV(C_SQUISH); (s)->dead = true; } while (0)

/* Solid.MoveHExact(move): riders ride along, an overlapped actor is pushed;
 * either way she gets the solid's LiftSpeed (x from this MoveH, y still 0) */
static void zip_move_h(State *s, Input in, int i, int move, float lx)
{
    int h = collider_h(s);
    bool rider = riding_zip(s, i);                            /* GetRiders() */
    int left = CUR_ZIP_BOX[i][0], right = CUR_ZIP_BOX[i][2];
    /* running the same way just above its top edge: pushed down 1 px, Actor.MoveV(1f) */
    if (in.mx == signi(move) && signf(s->spdX) == signi(move) && !rider) {
        zip_shift(i, move, -1);
        bool below = zip_overlap(i, s->x, s->y, h);
        zip_shift(i, -move, 1);
        if (below) { COV(C_ZIPNUDGE); move_v_plain(s, 1.0f); }
    }
    zip_shift(i, move, 0);
    short keep[4] = { CUR_ZIP_BOX[i][0], CUR_ZIP_BOX[i][1], CUR_ZIP_BOX[i][2], CUR_ZIP_BOX[i][3] };
    bool pushed = zip_overlap(i, s->x, s->y, h);
    if (pushed || rider) {
        int m = !pushed ? move : move > 0 ? move - ((s->x - 4) - right) : move - ((s->x + 4) - left);
        CUR_ZIP_BOX[i][0] = CUR_ZIP_BOX[i][2] = -32000;           /* Collidable = false */
        CUR_ZIP_BOX[i][1] = CUR_ZIP_BOX[i][3] = -32000;
        bool hit = move_h_exact(s, m);
        for (int k = 0; k < 4; k++) CUR_ZIP_BOX[i][k] = keep[k];
        if (pushed) { COV(C_ZIPPUSH); if (hit) SQUISH(s); } else COV(C_ZIPRIDE);
        set_lift(s, lx, 0.0f);
    }
}

/* Solid.MoveVExact(move): the same, LiftSpeed (x, y) of this MoveTo */
static void zip_move_v(State *s, int i, int move, float lx, float ly)
{
    int h = collider_h(s);
    bool rider = riding_zip(s, i);
    int top = CUR_ZIP_BOX[i][1], bottom = CUR_ZIP_BOX[i][3];
    zip_shift(i, 0, move);
    short keep[4] = { CUR_ZIP_BOX[i][0], CUR_ZIP_BOX[i][1], CUR_ZIP_BOX[i][2], CUR_ZIP_BOX[i][3] };
    bool pushed = zip_overlap(i, s->x, s->y, h);
    if (pushed || rider) {
        int m = !pushed ? move : move <= 0 ? move - (s->y - top) : move - ((s->y - h) - bottom);
        CUR_ZIP_BOX[i][0] = CUR_ZIP_BOX[i][2] = -32000;
        CUR_ZIP_BOX[i][1] = CUR_ZIP_BOX[i][3] = -32000;
        bool hit = move_v_exact(s, m);
        for (int k = 0; k < 4; k++) CUR_ZIP_BOX[i][k] = keep[k];
        if (pushed) { COV(C_ZIPPUSH); if (hit) SQUISH(s); } else COV(C_ZIPRIDE);
        set_lift(s, lx, ly);
    }
}

/* ZipMover.Update -> its Sequence() coroutine, one step (tables in room.h) */
static void zip_update(State *s, Input in)
{
    LOAD_WINDOW(s);
    for (int i = 0; i < NZIPMOVERS && !s->dead; i++) {
        int t = s->zipTimer[i];
        if (t != 0) t = t < ZIP_T_END ? t + 1 : 0;
        if (t == 0) {                                  /* while (!HasPlayerRider()) yield return null */
            if (riding_zip(s, i)) { COV(C_ZIPSTART); t = 1; }
            s->zipTimer[i] = (short)t;
            continue;
        }
        s->zipTimer[i] = (short)t;
        if (ZIP_MOVE[i][t][0] != 0) zip_move_h(s, in, i, ZIP_MOVE[i][t][0], ZIP_LIFT[i][t][0]);
        if (ZIP_MOVE[i][t][1] != 0) zip_move_v(s, i, ZIP_MOVE[i][t][1], ZIP_LIFT[i][t][0], ZIP_LIFT[i][t][1]);
        MODEL_ASSUME(CUR_ZIP_BOX[i][0] == ZIP_POS[i][t][0] && CUR_ZIP_BOX[i][1] == ZIP_POS[i][t][1]);
    }
}
#endif

/* ------------------------------------------------------------------------ */
/* Public API                                                               */
/* ------------------------------------------------------------------------ */
MODEL_API void celeste_init(State *s, int spawnX, int spawnY)
{
    State z = {0};
    *s = z;
    s->x = spawnX;
    s->y = spawnY;
    s->state = ST_NORMAL;
    s->facing = 1;
    s->dashes = MAX_DASHES;
    s->maxFall = MAX_FALL;
    s->stamina = CLIMB_MAX_STAMINA;
    WS_SET(s);
    s->aimX = 1;
}

/* VirtualButton.Update for Jump, Dash and Crouch Dash (runs every frame,
 * including freeze frames): bufferCounter -= dt; a key going down sets it to
 * BufferTime; a released button clears it. */
static void buttons_update(State *s, Input in)
{
    if (TPOS(s->jumpBuf)) TDEC(s->jumpBuf);
    s->jumpEdge = in.jump && (!s->prevJump || in.jump == BTN_REPRESS);
    if (s->jumpEdge) TSET(s->jumpBuf, INPUT_BUFFER_TIME);
    if (!in.jump) TCLR(s->jumpBuf);
    s->prevJump = in.jump != 0;

    if (TPOS(s->dashBuf)) TDEC(s->dashBuf);
    s->dashEdge = in.dash && (!s->prevDash || in.dash == BTN_REPRESS);
    if (s->dashEdge) TSET(s->dashBuf, INPUT_BUFFER_TIME);
    if (!in.dash) TCLR(s->dashBuf);
    s->prevDash = in.dash != 0;

    if (TPOS(s->cdashBuf)) TDEC(s->cdashBuf);
    s->cdashEdge = in.cdash && (!s->prevCDash || in.cdash == BTN_REPRESS);
    if (s->cdashEdge) TSET(s->cdashBuf, INPUT_BUFFER_TIME);
    if (!in.cdash) TCLR(s->cdashBuf);
    s->prevCDash = in.cdash != 0;
}

/* One frame: Engine.Update -> MInput.Update, then either a freeze frame or a
 * full scene update (only the player is simulated). */
MODEL_API void celeste_step(State *s, Input in)
{
    if (s->exited || s->dead) return;

    buttons_update(s, in);

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
#if NZIPMOVERS > 0
    if (!s->exited && !s->dead) zip_update(s, in);   /* entities added after her update after her */
#endif
}

#ifdef MODEL_PREFIX
#define MODEL_CAT2(p, n) p##_##n
#define MODEL_CAT(p, n) MODEL_CAT2(p, n)
void MODEL_CAT(MODEL_PREFIX, init)(State *s) { celeste_init(s, SPAWN_X, SPAWN_Y); }
void MODEL_CAT(MODEL_PREFIX, step)(State *s, Input in) { celeste_step(s, in); }
#endif
