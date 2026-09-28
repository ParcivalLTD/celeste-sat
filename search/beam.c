/*
 * beam.c -- fast heuristic search with the exact model (solver build). Keeps
 * the best K distinct states per frame and stops at the first frame where a
 * state leaves the room. The result is an upper bound (a real, replayable
 * route) that the SAT search then tries to beat and finally proves optimal.
 *
 *   beam [-k width] [-f maxframes] [-b dashbonus] [-r rollout] [-m percell]
 *        [-t tiebreak] [-p route.tas -n K] [-x exitX] out.tas
 *
 * -x only accepts leaving the room at that x (so the next room is entered
 * where its route starts).
 *
 * -p/-n start from the state after the first K frames of an existing route
 * (the output keeps those K frames): a focused search of the rest.
 *
 * Ranking: a pixel-level BFS over the room gives, for every position of
 * Madeline's hitbox, the length of the shortest free path to an exit (gravity
 * ignored) and the point 16 px further along that path. Each state is scored
 * by a short rollout that steers towards that point (so states in the middle
 * of a dash freeze, or about to jump, are valued by where they are going).
 *
 * Memory: only the current frontier is kept as full states; earlier frames
 * keep (parent, input) links for rebuilding the route. Uses OpenMP if built
 * with -fopenmp.
 */
#include <assert.h>
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _OPENMP
#include <omp.h>
#endif
#define MODEL_ASSUME(c) assert(c)
#define MODEL_THREADS
#include "../model/celeste.c"
#include "../sim/tas_io.h"
#ifdef START_STATE_FILE
#include START_STATE_FILE
#endif

/* ---- distance field over hitbox positions ------------------------------ */
#define GX0 0
#define GX1 ROOM_PX_W                 /* x in [GX0, GX1] */
#define GY0 (-16)
#define GY1 (ROOM_PX_H + 24)          /* y in [GY0, GY1] */
#define GW (GX1 - GX0 + 1)
#define GH (GY1 - GY0 + 1)
#define INF (1 << 29)
#define LOOK 16

static int dist[GH][GW];
static short aheadX[GH][GW], aheadY[GH][GW];   /* point LOOK px further along the path */

static bool solid_px(int px, int py)            /* tile solid at pixel; outside the grid is air */
{
    if (px < 0 || py < 0 || px >= ROOM_PX_W || py >= ROOM_PX_H) return false;
    return (ROOM_COLS[px >> 3] >> (py >> 3)) & 1u;
}

static bool box_free(int x, int y, int h)       /* 8 x h hitbox at (x - 4, y - h) */
{
    for (int py = y - h; py < y; py++)
        for (int px = x - 4; px < x + 4; px++)
            if (solid_px(px, py)) return false;
    return true;
}

/* 0 = cannot be here, 1 = free, 2 = leaving the room here counts as an exit */
static int classify(int x, int y)
{
    if (y - HB_NORMAL_H > ROOM_PX_H + 4) return 0;
    if (!box_free(x, y, HB_DUCK_H)) return 0;    /* most permissive hitbox */
    int cy2 = 2 * y - HB_NORMAL_H;
    if (x - 4 < 0)
        return (y - HB_NORMAL_H >= 0 && y < ROOM_PX_H && neighbour(EXIT_SIDE_LEFT, cy2) == 1) ? 2 : 0;
    if (x + 4 > ROOM_PX_W)
        return (y - HB_NORMAL_H >= 0 && y < ROOM_PX_H && neighbour(EXIT_SIDE_RIGHT, cy2) == 1) ? 2 : 0;
    if (cy2 < 0 && neighbour(EXIT_SIDE_UP, 2 * x)) return neighbour(EXIT_SIDE_UP, 2 * x) == 1 ? 2 : 0;
    if (y > ROOM_PX_H && neighbour(EXIT_SIDE_DOWN, 2 * x)) return neighbour(EXIT_SIDE_DOWN, 2 * x) == 1 ? 2 : 0;
    if (y - HB_NORMAL_H < -24) return 0;
    /* standing hurtbox on spikes: avoid */
    if (box_touches_spikes(x, y - 2, 9, 15)) return 0;
    return 1;
}

static int pos_dist(int x, int y, int *ax, int *ay);

static void build_distance(void)
{
    static signed char cls[GH][GW];
    static int qx[GW * GH], qy[GW * GH];
    static short nx_[GH][GW], ny_[GH][GW];
    int head = 0, tail = 0, ntarget = 0;
    for (int y = GY0; y <= GY1; y++)
        for (int x = GX0; x <= GX1; x++) {
            int c = classify(x, y);
            cls[y - GY0][x - GX0] = (signed char)c;
            dist[y - GY0][x - GX0] = INF;
            nx_[y - GY0][x - GX0] = (short)x; ny_[y - GY0][x - GX0] = (short)y;
            if (c == 2) { dist[y - GY0][x - GX0] = 0; qx[tail] = x; qy[tail++] = y; ntarget++; }
        }
    while (head < tail) {
        int x = qx[head], y = qy[head++];
        static const int d[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
        for (int k = 0; k < 4; k++) {
            int nx = x + d[k][0], ny = y + d[k][1];
            if (nx < GX0 || ny < GY0 || nx > GX1 || ny > GY1) continue;
            if (!cls[ny - GY0][nx - GX0]) continue;
            if (dist[ny - GY0][nx - GX0] > dist[y - GY0][x - GX0] + 1) {
                dist[ny - GY0][nx - GX0] = dist[y - GY0][x - GX0] + 1;
                nx_[ny - GY0][nx - GX0] = (short)x; ny_[ny - GY0][nx - GX0] = (short)y;   /* next step to the exit */
                qx[tail] = nx; qy[tail++] = ny;
            }
        }
    }
    for (int y = GY0; y <= GY1; y++)
        for (int x = GX0; x <= GX1; x++) {
            int cx = x, cy = y;
            for (int k = 0; k < LOOK; k++) {
                int a = nx_[cy - GY0][cx - GX0], b = ny_[cy - GY0][cx - GX0];
                cx = a; cy = b;
            }
            aheadX[y - GY0][x - GX0] = (short)cx;
            aheadY[y - GY0][x - GX0] = (short)cy;
        }
#ifdef START_STATE_FILE
    int sd = pos_dist(START_STATE.x, START_STATE.y, NULL, NULL);
#else
    int sd = dist[SPAWN_Y - GY0][SPAWN_X - GX0];
#endif
    fprintf(stderr, "distance field: %d exit positions, spawn is %d px from an exit\n",
            ntarget, sd >= INF ? -1 : sd);
}

/* distance of a position, or of the best one nearby (positions on spikes are
 * left out of the field) */
static int pos_dist(int x, int y, int *ax, int *ay)
{
    int best = INF, bx = x, by = y;
    for (int r = 0; r <= 3 && best >= INF; r++)
        for (int dy = -r; dy <= r; dy++)
            for (int dx = -r; dx <= r; dx++) {
                int xx = x + dx, yy = y + dy;
                if (xx < GX0 || yy < GY0 || xx > GX1 || yy > GY1) continue;
                int d = dist[yy - GY0][xx - GX0];
                if (d < INF && d + abs(dx) + abs(dy) < best) { best = d + abs(dx) + abs(dy); bx = xx; by = yy; }
            }
    if (ax) { *ax = best < INF ? aheadX[by - GY0][bx - GX0] : x; *ay = best < INF ? aheadY[by - GY0][bx - GX0] : y; }
    return best;
}

/* ---- rollout policy and score -------------------------------------------- */
static Input policy(const State *s)
{
    int tx, ty;
    pos_dist(s->x, s->y, &tx, &ty);
    Input in = {0, 0, 0, 0, false, 0};
    in.mx = (signed char)(tx > s->x + 1 ? 1 : (tx < s->x - 1 ? -1 : 0));
    bool up = ty < s->y - 1, down = ty > s->y + 1;
    unsigned char press = s->prevJump ? BTN_REPRESS : 1;
    if (s->state == ST_DASH && s->coStage <= 1) {     /* dash direction still to be read: aim at the path */
        in.my = (signed char)(up ? -1 : (down ? 1 : 0));
        if (TPOS(s->jumpGraceTimer) && !down && in.mx != 0)   /* on the ground: super (hyper if ducked) */
            in.jump = press;
        return in;
    }
    if (s->state == ST_CLIMB) {                        /* keep climbing while the path goes up */
        in.grab = up;
        in.my = (signed char)(up ? -1 : 0);
        in.mx = 0;
    } else if (up) {
        in.jump = s->onGround ? !s->prevJump : 1;
        if (s->state == ST_DASH) {                     /* at a wall: climb jump out of the dash */
            in.grab = true;
            in.jump = press;
        }
    }
    return in;
}

static int EXIT_X = -1;          /* -x: only count exits at this x (to line up with the next room's route) */
static float DASH_BONUS = 0.0f;
static int ROLLOUT = 10;
static float TIE = 0.0f;         /* -t: prefer states that reach their best distance sooner */
static float score(const State *s0)
{
    if (s0->exited) return 1e9f;
    State s = *s0;
    float best = -(float)pos_dist(s.x, s.y, NULL, NULL);
    int tbest = 0;
    for (int t = 1; t <= ROLLOUT; t++) {
        celeste_step(&s, policy(&s));
        if (s.dead) break;
        if (s.exited) return 1e6f - (float)t;
        float v = -(float)pos_dist(s.x, s.y, NULL, NULL);
        if (v > best) { best = v; tbest = t; }
    }
    return best - TIE * (float)tbest + (s0->dashes > 0 ? DASH_BONUS : 0.0f);
}

static uint64_t hash_state(const State *s)
{
    /* hash every field that influences the future */
    uint64_t h = 1469598103934665603ULL;
#define MIX(v) do { uint64_t _v = (uint64_t)(v); h ^= _v; h *= 1099511628211ULL; } while (0)
#define MIXF(f) do { uint32_t _u; float _f = (f); memcpy(&_u, &_f, 4); MIX(_u); } while (0)
    MIX(s->x); MIX(s->y); MIXF(s->remX); MIXF(s->remY); MIXF(s->spdX); MIXF(s->spdY);
    MIX(s->state); MIX(s->facing); MIX(s->ducking); MIX(s->onGround); MIX(s->dashes);
    MIX(s->moveX); MIX(s->forceMoveX); MIX(s->wallSlideDir); MIX(s->autoJump); MIX(s->dashStartedOnGround);
    MIX(s->aimX); MIX(s->aimY); MIX(s->dashDirX); MIX(s->dashDirY);
    MIXF(s->beforeDashSpdX); MIXF(s->beforeDashSpdY); MIXF(s->varJumpSpeed); MIXF(s->wallSpeedRetained); MIXF(s->maxFall);
    MIXF(s->stamina); MIX(s->wallBoostDir); MIX(s->lastClimbMove); MIX(s->hopWaitX);
    MIX(s->wallBoostTimer); MIX(s->climbNoMoveTimer);
    MIX(s->jumpGraceTimer); MIX(s->varJumpTimer); MIX(s->varJumpLong); MIX(s->dashCooldownTimer);
    MIX(s->dashRefillCooldownTimer); MIX(s->dashAttackTimer); MIX(s->wallSlideTimer);
    MIX(s->wallSpeedRetentionTimer); MIX(s->forceMoveXTimer); MIX(s->coActive); MIX(s->coStage); MIX(s->coWait);
    MIX(s->freezeTimer); MIX(s->prevJump); MIX(s->prevDash); MIX(s->prevCDash);
    MIX(s->jumpBuf); MIX(s->dashBuf); MIX(s->cdashBuf);
    return h;
}

/* ---- search -------------------------------------------------------------- */
#define MAXC (3 * 3 * 3 * 3 * 2)   /* candidate inputs per state */
typedef struct { float score; int parent; uint16_t in; } Cand;
typedef struct { int parent; uint16_t in; } Link;

static uint16_t pack(Input in)
{
    return (uint16_t)((in.mx + 1) | ((in.my + 1) << 2) | (in.jump << 4) | (in.dash << 6) | (in.grab << 8)
                      | (in.cdash << 9));
}
static Input unpack(uint16_t b)
{
    Input in = { (signed char)((b & 3) - 1), (signed char)(((b >> 2) & 3) - 1),
                 (unsigned char)((b >> 4) & 3), (unsigned char)((b >> 6) & 3), (bool)((b >> 8) & 1),
                 (unsigned char)((b >> 9) & 3) };
    return in;
}

static int cmp_cand(const void *a, const void *b)
{
    const Cand *x = a, *y = b;
    if (x->score != y->score) return x->score < y->score ? 1 : -1;
    if (x->parent != y->parent) return x->parent < y->parent ? -1 : 1;
    return (int)x->in - (int)y->in;
}

/* lock-free open-addressing set of state hashes (dedup within one frame) */
static uint64_t *seen; static size_t seen_mask;
static int seen_insert(uint64_t h)
{
    if (!h) h = 1;
    size_t i = h & seen_mask;
    for (;;) {
        uint64_t v = __atomic_load_n(&seen[i], __ATOMIC_RELAXED);
        if (v == 0) {
            uint64_t expected = 0;
            if (__atomic_compare_exchange_n(&seen[i], &expected, h, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED))
                return 1;
            v = expected;
        }
        if (v == h) return 0;
        i = (i + 1) & seen_mask;
    }
}

/* per-cell cap: at most M kept states per (x, y, state, dashes, onGround) */
static uint64_t cell_key(const State *s)
{
    return ((uint64_t)(uint16_t)s->x << 32) | ((uint64_t)(uint16_t)s->y << 16)
         | ((uint64_t)s->state << 4) | ((uint64_t)s->dashes << 1) | (uint64_t)s->onGround;
}

int main(int argc, char **argv)
{
    int K = 20000, maxFrames = 600, M = 0, prefixN = 0;
    const char *out = "beam.tas", *prefixFile = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-k")) K = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-f")) maxFrames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-b")) DASH_BONUS = (float)atof(argv[++i]);
        else if (!strcmp(argv[i], "-r")) ROLLOUT = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-t")) TIE = (float)atof(argv[++i]);
        else if (!strcmp(argv[i], "-m")) M = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-p")) prefixFile = argv[++i];
        else if (!strcmp(argv[i], "-n")) prefixN = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-x")) EXIT_X = atoi(argv[++i]);
        else out = argv[i];
    }
    build_distance();

    State *cur = malloc(sizeof(State) * K), *nxt = malloc(sizeof(State) * K);
    Link **hist = calloc(maxFrames + 1, sizeof *hist);
    int ncur = 1;
#ifdef START_STATE_FILE
    cur[0] = START_STATE;
#else
    celeste_init(&cur[0], SPAWN_X, SPAWN_Y);
#endif
    static Input prefix[4096];
    if (prefixFile) {
        int n = tas_load(prefixFile, prefix, 4096);
        if (prefixN > n) prefixN = n;
        for (int t = 0; t < prefixN; t++) {
            celeste_step(&cur[0], prefix[t]);
            if (cur[0].exited || cur[0].dead) { fprintf(stderr, "prefix ends the run at frame %d\n", t + 1); return 2; }
        }
    } else {
        prefixN = 0;
    }

    Cand *cand = NULL; size_t candCap = 0;
    uint64_t *ckeys = NULL; unsigned char *ccount = NULL; size_t cmask = 0;
    if (M > 0) {
        size_t c = 1; while (c < (size_t)K * 4) c <<= 1;
        ckeys = calloc(c, sizeof *ckeys); ccount = calloc(c, 1); cmask = c - 1;
    }

    for (int f = 0; f < maxFrames; f++) {
        size_t maxc = (size_t)ncur * MAXC + 16;
        if (maxc > candCap) {
            candCap = maxc;
            cand = realloc(cand, candCap * sizeof *cand);
            size_t sc = 1; while (sc < candCap * 2) sc <<= 1;
            free(seen); seen = malloc(sc * sizeof *seen); seen_mask = sc - 1;
            if (!cand || !seen) { fprintf(stderr, "out of memory at frame %d\n", f); return 2; }
        }
        memset(seen, 0, (seen_mask + 1) * sizeof *seen);
        size_t nc = 0;

        #pragma omp parallel for schedule(dynamic, 32)
        for (int i = 0; i < ncur; i++) {
            Cand local[MAXC]; int nl = 0;
            State cs = cur[i];
            bool frozen = cs.freezeTimer > 0;
            bool upMatters = (cs.state == ST_DASH && cs.coStage == 1) || cs.state == ST_CLIMB;
            load_window(&cs);
            /* grab can only matter next to a wall (exact duplicates are dropped below anyway) */
            bool grabMatters = !frozen && (cs.state == ST_CLIMB || grab_near_wall(&cs));
            /* Button options (see harness/solve.c for why these lose nothing):
             * jump: release, hold (a press after a release), or press again
             * while held -- kept only if it jumps right away; dash / crouch
             * dash: a press, kept only if a dash starts on this frame. */
            unsigned char jumpOpts[3] = {0, 1, 2}, nj = cs.prevJump ? 3 : 2;
            unsigned char press = cs.prevDash ? BTN_REPRESS : 1, cpress = cs.prevCDash ? BTN_REPRESS : 1;
            for (int mx = -1; mx <= 1; mx++)
            for (int my = -1; my <= 1; my++)
            for (int jo = 0; jo < nj; jo++)
            for (int dk = 0; dk < 3; dk++)               /* 0 none, 1 dash, 2 crouch dash */
            for (int g = 0; g <= 1; g++) {
                if (frozen && (mx != 0 || my != 0 || g)) continue;
                if (my == -1 && !upMatters) continue;
                if (g && !grabMatters) continue;
                Input in = { (signed char)mx, (signed char)my, jumpOpts[jo],
                             (unsigned char)(dk == 1 ? press : 0), (bool)g, (unsigned char)(dk == 2 ? cpress : 0) };
                State n = cs;
                celeste_step(&n, in);
                if (n.dead) continue;
                if (n.exited && EXIT_X >= 0 && n.x != EXIT_X) continue;
                if (in.jump == BTN_REPRESS && TPOS(n.jumpBuf)) continue;   /* pressed again for nothing */
                if (dk && (TPOS(n.dashBuf) || TPOS(n.cdashBuf))) continue; /* no dash started */
                if (!seen_insert(hash_state(&n))) continue;
                local[nl].score = score(&n);
                local[nl].parent = i;
                local[nl].in = pack(in);
                nl++;
            }
            size_t at = __atomic_fetch_add(&nc, (size_t)nl, __ATOMIC_RELAXED);
            memcpy(cand + at, local, nl * sizeof(Cand));
        }
        if (!nc) { printf("beam: every state died by frame %d\n", f + 1); return 1; }
        qsort(cand, nc, sizeof(Cand), cmp_cand);

        /* keep the best K (at most M per cell) */
        Link *links = malloc(sizeof(Link) * (nc < (size_t)K ? nc : (size_t)K));
        int nk = 0;
        if (M > 0) {
            memset(ccount, 0, cmask + 1);
            memset(ckeys, 0, (cmask + 1) * sizeof *ckeys);
        }
        for (size_t c = 0; c < nc && nk < K; c++) {
            if (M > 0) {
                State t = cur[cand[c].parent];
                celeste_step(&t, unpack(cand[c].in));
                uint64_t key = cell_key(&t) + 1;
                size_t h = (key * 0x9E3779B97F4A7C15ULL) & cmask;
                while (ckeys[h] && ckeys[h] != key) h = (h + 1) & cmask;
                ckeys[h] = key;
                if (ccount[h] >= M) continue;
                ccount[h]++;
            }
            links[nk].parent = cand[c].parent;
            links[nk].in = cand[c].in;
            nk++;
        }
        hist[f + 1] = links;
        #pragma omp parallel for schedule(static)
        for (int k = 0; k < nk; k++) {
            nxt[k] = cur[links[k].parent];
            celeste_step(&nxt[k], unpack(links[k].in));
        }
        if (getenv("BEAM_VERBOSE"))
            fprintf(stderr, "frame %3d: %8zu states, best at (%d,%d) score %.1f\n", f + 1, nc,
                    nxt[0].x, nxt[0].y, cand[0].score);

        if (nxt[0].exited) {
            int frames = prefixN + f + 1;
            Input *seq = malloc(frames * sizeof(Input));
            memcpy(seq, prefix, prefixN * sizeof(Input));
            for (int t = f + 1, idx = 0; t > 0; t--) { seq[prefixN + t - 1] = unpack(hist[t][idx].in); idx = hist[t][idx].parent; }
            FILE *fo = fopen(out, "w");
            if (prefixN) fprintf(fo, "# beam search (width %d) after the first %d frames of %s: exits on frame %d\n",
                                 K, prefixN, prefixFile, frames);
            else fprintf(fo, "# beam search (width %d): exits on frame %d\n", K, frames);
            tas_write(fo, seq, frames);
            fclose(fo);
            printf("beam: exit on frame %d -> %s\n", frames, out);
            return 0;
        }
        State *tmp = cur; cur = nxt; nxt = tmp;
        ncur = nk;
    }
    printf("beam: no exit within %d frames\n", maxFrames);
    return 1;
}
