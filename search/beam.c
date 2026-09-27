/*
 * beam.c -- fast heuristic search with the exact model (solver build). Keeps
 * the best K distinct states per frame, ranked by distance to the exit, and
 * stops at the first frame where a state leaves the room. The result is an
 * upper bound (a real, replayable solution) that the SAT search then tries to
 * beat and finally proves optimal.
 *
 *   beam [-k width] [-f maxframes] out.tas
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MODEL_ASSUME(c) assert(c)
#include "../model/celeste.c"

typedef struct { State s; int parent; Input in; double score; } Node;

/* tile distance (BFS over free tiles) to the exit column, for the heuristic */
static int dist[ROOM_H][ROOM_W];

static void build_distance(void)
{
    int qx[ROOM_W * ROOM_H], qy[ROOM_W * ROOM_H], head = 0, tail = 0;
    for (int y = 0; y < ROOM_H; y++)
        for (int x = 0; x < ROOM_W; x++) dist[y][x] = 1 << 20;
    for (int y = 0; y < ROOM_H; y++)
        if (!((col_bits(ROOM_W - 1) >> (y)) & 1u)) { dist[y][ROOM_W - 1] = 0; qx[tail] = ROOM_W - 1; qy[tail++] = y; }
    while (head < tail) {
        int x = qx[head], y = qy[head++];
        static const int d[4][2] = {{1,0},{-1,0},{0,1},{0,-1}};
        for (int k = 0; k < 4; k++) {
            int nx = x + d[k][0], ny = y + d[k][1];
            if (nx < 0 || ny < 0 || nx >= ROOM_W || ny >= ROOM_H || ((col_bits(nx) >> (ny)) & 1u)) continue;
            if (dist[ny][nx] > dist[y][x] + 1) { dist[ny][nx] = dist[y][x] + 1; qx[tail] = nx; qy[tail++] = ny; }
        }
    }
}

static double pixels_to_go(const State *s)
{
    int cx = s->x >> 3, cy = (s->y - 1) >> 3;
    if (cx < 0) cx = 0;
    if (cx >= ROOM_W) cx = ROOM_W - 1;
    if (cy < 0) cy = 0;
    if (cy >= ROOM_H) cy = ROOM_H - 1;
    return dist[cy][cx] * 8.0 - (s->x & 7);
}

/* Rank a state by a short rollout (hold right, tap jump when grounded) so that
 * states in the middle of a dash freeze are not undervalued. Higher = better. */
#define ROLLOUT 8
static double score(const State *s0)
{
    if (s0->exited) return 1e9;
    State s = *s0;
    double best = -pixels_to_go(&s);
    for (int t = 1; t <= ROLLOUT; t++) {
        Input in = { 1, 0, (bool)(s.onGround || s.varJumpTimer > 0), false };
        celeste_step(&s, in);
        if (s.dead) break;
        if (s.exited) return 1e6 - t;
        double v = -pixels_to_go(&s);
        if (v > best) best = v;
    }
    return best + 0.01 * s0->spdX + (s0->dashes > 0 ? 2.0 : 0.0);
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
    MIX(s->jumpGraceTimer); MIX(s->varJumpTimer); MIX(s->varJumpLong); MIX(s->dashCooldownTimer);
    MIX(s->dashRefillCooldownTimer); MIX(s->dashAttackTimer); MIX(s->wallSlideTimer);
    MIX(s->wallSpeedRetentionTimer); MIX(s->forceMoveXTimer); MIX(s->coActive); MIX(s->coStage); MIX(s->coWait);
    MIX(s->freezeTimer); MIX(s->prevJump); MIX(s->prevDash); MIX(s->jumpBuf); MIX(s->dashBuf);
    return h;
}

static int cmp_node(const void *a, const void *b)
{
    double sa = ((const Node *)a)->score, sb = ((const Node *)b)->score;
    return sa < sb ? 1 : (sa > sb ? -1 : 0);
}

/* open-addressing set of hashes for dedup within one frame */
static uint64_t *seen; static size_t seen_cap;
static int seen_insert(uint64_t h)
{
    if (!h) h = 1;
    size_t i = h & (seen_cap - 1);
    while (seen[i]) { if (seen[i] == h) return 0; i = (i + 1) & (seen_cap - 1); }
    seen[i] = h;
    return 1;
}

int main(int argc, char **argv)
{
    int K = 20000, maxFrames = 400;
    const char *out = "beam.tas";
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-k")) K = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-f")) maxFrames = atoi(argv[++i]);
        else out = argv[i];
    }
    build_distance();

    Node **layers = calloc(maxFrames + 1, sizeof *layers);
    int *count = calloc(maxFrames + 1, sizeof *count);
    layers[0] = malloc(sizeof(Node));
    celeste_init(&layers[0][0].s, SPAWN_X, SPAWN_Y);
    layers[0][0].parent = -1;
    count[0] = 1;

    size_t candCap = 0;
    Node *cand = NULL;
    seen_cap = 0; seen = NULL;

    for (int f = 0; f < maxFrames; f++) {
        size_t need = (size_t)count[f] * 36 + 16;
        if (need > candCap) {
            candCap = need;
            cand = realloc(cand, candCap * sizeof(Node));
            size_t sc = 1; while (sc < candCap * 2) sc <<= 1;
            if (sc > seen_cap) { seen_cap = sc; seen = realloc(seen, seen_cap * sizeof *seen); }
            if (!cand || !seen) { fprintf(stderr, "out of memory at frame %d\n", f); return 2; }
        }
        size_t nc = 0;
        memset(seen, 0, seen_cap * sizeof *seen);
        for (int i = 0; i < count[f]; i++) {
            const State *cur = &layers[f][i].s;
            bool frozen = cur->freezeTimer > 0;
            bool upMatters = cur->state == ST_DASH && cur->coStage == 1;
            for (int mx = -1; mx <= 1; mx++)
            for (int my = -1; my <= 1; my++)
            for (int j = 0; j <= 1; j++)
            for (int d = 0; d <= 1; d++) {
                if (frozen && (mx != 0 || my != 0)) continue;
                if (my == -1 && !upMatters) continue;
                if (d && cur->prevDash && cur->dashBuf < 2) continue;
                Input in = { (signed char)mx, (signed char)my, j, d };
                Node n;
                n.s = *cur;
                celeste_step(&n.s, in);
                if (n.s.dead) continue;
                if (!seen_insert(hash_state(&n.s))) continue;
                n.parent = i; n.in = in; n.score = score(&n.s);
                cand[nc++] = n;
            }
        }
        if (getenv("BEAM_VERBOSE")) fprintf(stderr, "frame %3d: %zu distinct states\n", f + 1, nc);
        qsort(cand, nc, sizeof(Node), cmp_node);
        if (nc > (size_t)K) nc = K;
        layers[f + 1] = malloc(nc * sizeof(Node));
        memcpy(layers[f + 1], cand, nc * sizeof(Node));
        count[f + 1] = (int)nc;

        if (nc && layers[f + 1][0].s.exited) {
            int frames = f + 1;
            Input *seq = malloc(frames * sizeof(Input));
            for (int t = frames, idx = 0; t > 0; t--) { seq[t - 1] = layers[t][idx].in; idx = layers[t][idx].parent; }
            FILE *fo = fopen(out, "w");
            fprintf(fo, "# beam search (width %d): exits on frame %d\n", K, frames);
            for (int t = 0; t < frames;) {
                int u = t; while (u < frames && !memcmp(&seq[u], &seq[t], sizeof(Input))) u++;
                fprintf(fo, "%4d", u - t);
                if (seq[t].mx < 0) fprintf(fo, ",L"); if (seq[t].mx > 0) fprintf(fo, ",R");
                if (seq[t].my < 0) fprintf(fo, ",U"); if (seq[t].my > 0) fprintf(fo, ",D");
                if (seq[t].jump) fprintf(fo, ",J"); if (seq[t].dash) fprintf(fo, ",X");
                fprintf(fo, "\n");
                t = u;
            }
            fclose(fo);
            printf("beam: exit on frame %d -> %s\n", frames, out);
            return 0;
        }
    }
    printf("beam: no exit within %d frames\n", maxFrames);
    return 1;
}
