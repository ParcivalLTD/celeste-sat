/*
 * tas_io.h -- CelesteTAS-style input files, shared by sim and beam.
 *
 * A line is "  12,R,J": a frame count, then the keys held on those frames.
 * L R U D are the directions, J and K the two jump keys, X and C the two
 * dash keys, Z and V the two crouch dash keys, G and H grab. As in the game,
 * a button is pressed on a frame where any of its keys goes down, so
 * alternating J and K presses jump on consecutive frames without ever
 * releasing it (see Input in celeste.h).
 * Lines starting with '#' are comments.
 */
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* button value from the two keys now and on the previous frame */
static unsigned char tas_button(const bool now[2], bool prev[2])
{
    bool held = now[0] || now[1], wasHeld = prev[0] || prev[1];
    bool press = (now[0] && !prev[0]) || (now[1] && !prev[1]);
    prev[0] = now[0]; prev[1] = now[1];
    if (!held) return 0;
    return wasHeld && press ? BTN_REPRESS : 1;
}

static int tas_load(const char *path, Input *buf, int cap)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(1); }
    char line[512];
    int n = 0;
    bool pj[2] = {false, false}, pd[2] = {false, false}, pz[2] = {false, false};
    while (fgets(line, sizeof line, f)) {
        char *p = line;
        while (isspace((unsigned char)*p)) p++;
        if (*p == '#' || *p == 0) continue;
        int count = atoi(p);
        if (count <= 0) continue;
        Input in = {0};
        bool j[2] = {false, false}, d[2] = {false, false}, z[2] = {false, false};
        for (char *q = strchr(p, ','); q; q = strchr(q + 1, ',')) {
            char *t = q + 1;
            while (*t == ' ') t++;
            char c = (char)toupper((unsigned char)*t);
            if (c == 'L') in.mx = -1;
            else if (c == 'R') in.mx = 1;
            else if (c == 'U') in.my = -1;
            else if (c == 'D') in.my = 1;
            else if (c == 'J') j[0] = true;
            else if (c == 'K') j[1] = true;
            else if (c == 'X') d[0] = true;
            else if (c == 'C') d[1] = true;
            else if (c == 'Z') z[0] = true;
            else if (c == 'V') z[1] = true;
            else if (c == 'G' || c == 'H') in.grab = true;
            else if (c && !isspace((unsigned char)c)) {
                fprintf(stderr, "%s: input '%c' is not modelled (line: %s)", path, c, p);
                exit(2);
            }
        }
        for (int i = 0; i < count && n < cap; i++) {
            buf[n] = in;
            buf[n].jump = tas_button(j, pj);
            buf[n].dash = tas_button(d, pd);
            buf[n].cdash = tas_button(z, pz);
            n++;
        }
    }
    fclose(f);
    return n;
}

/* the keys of each frame: a fresh press uses J (X), a press while the button
 * is held switches to the other key */
static int tas_next_key(unsigned char b, int cur)
{
    if (!b) return -1;
    if (cur < 0) return 0;
    return b == BTN_REPRESS ? 1 - cur : cur;
}

static void tas_keys(const Input *seq, int n, char (*keys)[8])
{
    int jk = -1, dk = -1, zk = -1;
    for (int t = 0; t < n; t++) {
        const Input *in = &seq[t];
        jk = tas_next_key(in->jump, jk);
        dk = tas_next_key(in->dash, dk);
        zk = tas_next_key(in->cdash, zk);
        char *k = keys[t];
        int m = 0;
        if (in->mx < 0) k[m++] = 'L';
        if (in->mx > 0) k[m++] = 'R';
        if (in->my < 0) k[m++] = 'U';
        if (in->my > 0) k[m++] = 'D';
        if (jk >= 0) k[m++] = "JK"[jk];
        if (dk >= 0) k[m++] = "XC"[dk];
        if (zk >= 0) k[m++] = "ZV"[zk];
        if (in->grab) k[m++] = 'G';
        k[m] = 0;
    }
}

static void tas_write(FILE *fo, const Input *seq, int n)
{
    char (*keys)[8] = malloc((size_t)(n ? n : 1) * sizeof *keys);
    tas_keys(seq, n, keys);
    for (int t = 0; t < n;) {
        int u = t;
        while (u < n && !strcmp(keys[u], keys[t])) u++;
        fprintf(fo, "%4d", u - t);
        for (const char *c = keys[t]; *c; c++) fprintf(fo, ",%c", *c);
        fprintf(fo, "\n");
        t = u;
    }
    free(keys);
}
