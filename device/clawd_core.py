# Clawd: a desk pet that follows your day. tools/deploy.py compiles this to /flash/clawd_core.mpy
# (the device can't compile a file this size) and device/main.py imports it at boot. See README.md.

import builtins   # clawd_buf / clawd_res are published here; they survive Ctrl-C (see tools/boot_check.py)
import json
import random
import socket
import time

import M5
import machine
import network
from hardware import MatrixKeyboard

LAT, LON = 51.51, -0.13   # weather location (London)

L = M5.Lcd
W, H = 240, 135
TOP, PH, FLOOR, U = 21, 97, 86, 4
SY = FLOOR - 10 * U

OR = 0xD77757
BK = 0x000000
CR = 0xF0EEE6
DK = 0x1F1F1F
GR = 0x777777
FC = 0x5B9BD5
PK = 0xFF6B8B
YL = 0xFFD166
GN = 0x6BCB77
RD = 0xE63946
BL = 0x3B5BA5
BL2 = 0x5B7BC5
WD = 0x8B5A2B
WD2 = 0x5E3B1E
MET = 0x444444
POP = 0xFFF3B0
CODE = (0xC678DD, 0x61AFEF, 0x98C379, 0xE5C07B, 0xABB2BF, OR)

SLEEP, COFFEE, WORK, EAT, GYM, TV, PLAY, READ, COMMUTE, BIKE, VOLLEY, CART, DANCE, YOGA, MUSIC = range(15)
FIXED = (SLEEP, TV, READ, COMMUTE, BIKE, VOLLEY, YOGA, MUSIC)   # Clawd stays at HOME, no walking
SIDES = (BIKE, GYM, VOLLEY, CART, DANCE, YOGA, MUSIC)
CYCLE = (None,) + SIDES   # arrow keys step through this; None = the scheduled activity
SIDE_MS = 600000
NET_MS = 3600000   # weather refresh interval
SCHED = ((420, SLEEP), (510, COFFEE), (570, COMMUTE), (600, COFFEE), (690, WORK),
         (780, EAT), (900, COFFEE), (1050, WORK), (1110, COMMUTE), (1140, GYM),
         (1200, EAT), (1290, TV), (1350, PLAY), (1380, READ), (1440, SLEEP))
LABEL = ("sleeping", "coffee", "working", "lunch", "workout", "tv time", "playtime", "reading",
         "commute", "bike ride", "volleyball", "cartwheels", "dancing", "yoga", "music")
HOME = (36, 56, 44, 44, 84, 40, 84, 70, 84, 84, 24, 84, 84, 84, 50)
EVENTS = (("dream", "roll"), ("wander", "look", "stretch", "hop"),
          ("think", "ship", "bug", "idea", "stretch", "look", "wander"),
          ("look", "hop"), (), ("laugh", "popcorn", "look"), (), ("yawn", "page"),
          (), (), (), (), (), (), ())
# Per-minute stat changes by scene:
#        SLP   COF   WRK    EAT   GYM   TV    PLAY  READ  COM   BIKE  VOL   CART  DANC  YOGA  MUS
F_RATE = (-0.1, -0.5, -0.5,  2.0, -0.7, -0.5, -0.6, -0.4, -0.7, -0.7, -0.7, -0.7, -0.7, -0.5, -0.5)
E_RATE = (0.5,  0.3,  -0.2, -0.2, -0.6, -0.1, -0.4, -0.1, -0.6, -0.6, -0.6, -0.6, -0.6, 0.1, 0.1)
J_RATE = (0.0,  -0.1, -0.35, 0.2, -0.1, 1.2,  1.2,  0.2,  0.0,  0.8,  1.2,  1.2,  1.2,  0.5, 1.2)
S_RATE = (-0.06, -0.06, -0.06, -0.06, 1.5, -0.06, 0.4, -0.06, 1.2, 1.2, 1.2, 1.0, 0.8, 0.6, -0.06)
DUR = {"wander": 170, "look": 48, "stretch": 36, "hop": 20, "think": 80, "ship": 45,
       "bug": 70, "idea": 40, "dream": 90, "roll": 40, "laugh": 32, "popcorn": 24,
       "yawn": 36, "page": 14}
BUBBLES = {"bug": "?", "idea": "!", "dream": "fish", "laugh": "ha!", "yawn": "zz"}
HELP = (("a-z", "feed him a fish"), ("space", "pet him"), ("arrows", "change activity"),
        ("1430 enter", "jump to 14:30"), ("enter", "back to live time"),
        ("tab", "mute / unmute"), ("? or esc", "show / hide keys"))
GREET = {"xmas": "ho ho", "newyear": "yay!", "valentine": "<3", "easter": "eggs!",
         "halloween": "boo!", "bonfire": "bang!"}
ARROWS = {0x2C: -1, 0x3B: -1, 0x2E: 1, 0x2F: 1, 180: -1, 181: -1, 182: 1, 183: 1}

CHIRPS = (((1047, 90), (1319, 120)), ((1319, 80), (1047, 110)),
          ((880, 70), (1047, 70), (1319, 110)), ((1568, 90), (1319, 90), (1047, 120)),
          ((1047, 50), (0, 40), (1047, 50), (1397, 130)), ((784, 80), (988, 80), (1175, 140)),
          ((1319, 70), (1175, 70), (1047, 70), (880, 140)), ((1760, 60), (1568, 60), (1760, 120)))
NOM = ((523, 60), (0, 30), (659, 70))
FULL = ((392, 90), (0, 30), (262, 200))
PET = ((1319, 50), (1760, 90))
JINGLE = ((784, 80), (988, 80), (1175, 80), (1568, 180))
WAKE = ((1047, 100), (1319, 100), (1568, 100), (2093, 220))
DANCE_TUNE = ((784, 120), (0, 40), (784, 120), (988, 120), (1175, 240), (988, 120), (1175, 300))
MUSIC_TUNE = ((659, 150), (784, 150), (880, 300), (784, 150), (659, 150), (587, 300), (523, 400))
SIGH = ((587, 120), (440, 220))
SAVE = "/flash/clawd.dat"


def rnd(n):
    return random.getrandbits(16) % n


def cap(v):
    return 0.0 if v < 0 else 100.0 if v > 100 else v


# Sprite: the Claude Code logo crab on an 18x5 grid, each cell U wide and 2U tall.
_PC = {}


def rows(eyes, arms, legs):
    r0 = "...############..."
    r1 = {"c": "...##o######o##...", "l": "...#o######o###...",
          "r": "...###o######o#...", "x": "...##-######-##..."}[eyes]
    r2 = ".################."
    r3 = "...############..."
    r4 = ("....#.#....#.#....", ".....#.#..#.#.....")[legs]
    if arms == "up":
        r0 = ".#." + r0[3:15] + ".#."
        r1 = ".#." + r1[3:15] + ".#."
        r2 = r3
    elif arms == "down":
        r2, r3 = r3, r2
    elif arms == "mug":
        r0 = r0[:15] + ".#."
        r1 = r1[:15] + ".#."
        r2 = ".##############..."
    return r0, r1, r2, r3, r4


def pose(eyes, arms, legs, rot):
    key = (eyes, arms, legs, rot)
    p = _PC.get(key)
    if p is None:
        p = []
        for r, row in enumerate(rows(eyes, arms, legs)):
            c = 0
            while c < 18:
                ch = row[c]
                n = 1
                while ch == "#" and c + n < 18 and row[c + n] == "#":
                    n += 1
                if ch != ".":
                    k = "#o-".index(ch)
                    if rot == 0:
                        p.append((c * U, r * 2 * U, n * U, 2 * U, k))
                    elif rot == 1:
                        p.append(((4 - r) * 2 * U, c * U, 2 * U, n * U, k))
                    elif rot == 2:
                        p.append(((18 - c - n) * U, (4 - r) * 2 * U, n * U, 2 * U, k))
                    else:
                        p.append((r * 2 * U, (18 - c - n) * U, 2 * U, n * U, k))
                c += n
        _PC[key] = p
    return p


def cl(C, g, x, y, eyes="c", arms="side", legs=0, rot=0, col=OR):
    if col == OR:
        g.hx = x + (20 if rot % 2 else 36)
        g.hy = y
    for rx, ry, rw, rh, k in pose(eyes, arms, legs, rot):
        if k == 1:
            C.fillRect(x + rx, y + ry, rw, rh, BK)
        else:
            C.fillRect(x + rx, y + ry, rw, rh, col)
            if k == 2:
                C.fillRect(x + rx, y + ry + rh // 2, rw, 2, BK)
    if col == OR and not rot and g.hol and g.scene != COMMUTE:
        hat(C, g.hol, x, y)


def auto(C, g, f, arms="side", eyes=None, dx=0):
    moving = g.x != g.tx
    if moving:
        eyes = "r" if g.dir > 0 else "l"
    elif g.ev == "look":
        eyes = "lcr"[(g.ev_t // 12) % 3]
    elif eyes is None:
        eyes = "c"
    if g.ev == "stretch":
        arms, eyes = "up", "x"
    if g.eat_t:
        arms = "up"
        eyes = "x" if (g.eat_t // 3) % 2 else "c"
    elif g.happy:
        arms, eyes = "up", "x"
    elif f % 50 < 2:
        eyes = "x"
    if g.jy and arms == "side":
        arms = "up"
    legs = (f // 4) % 2 if moving or g.jy else 0
    cl(C, g, g.x + dx, SY + g.jy, eyes, arms, legs)


def heart(C, x, y, c):
    C.fillCircle(x - 2, y, 2, c)
    C.fillCircle(x + 2, y, 2, c)
    C.fillTriangle(x - 4, y + 1, x + 4, y + 1, x, y + 5, c)


def note(C, x, y, c):
    C.fillEllipse(x, y + 6, 3, 2, c)
    C.fillRect(x + 2, y - 2, 1, 8, c)
    C.fillRect(x + 2, y - 2, 4, 2, c)


def drop(C, x, y):
    C.fillCircle(x, y, 2, 0x8ECAE6)
    C.fillTriangle(x - 2, y, x + 2, y, x, y - 4, 0x8ECAE6)


def fish(C, x, y, c, flip):
    if flip:
        C.fillEllipse(x + 7, y + 4, 7, 4, c)
        C.fillTriangle(x + 18, y, x + 18, y + 8, x + 13, y + 4, c)
        C.fillRect(x + 3, y + 2, 2, 2, BK)
    else:
        C.fillEllipse(x + 11, y + 4, 7, 4, c)
        C.fillTriangle(x, y, x, y + 8, x + 5, y + 4, c)
        C.fillRect(x + 13, y + 2, 2, 2, BK)


def bell(C, cx, cy):
    C.fillRect(cx - 5, cy - 1, 10, 2, 0x999999)
    C.fillRect(cx - 6, cy - 4, 3, 8, MET)
    C.fillRect(cx + 3, cy - 4, 3, 8, MET)


def spawn(g, k, x, y, vx, vy, life, col=0):
    if len(g.parts) < 16:
        g.parts.append([k, x, y, vx, vy, life, col])


def particles(C, g):
    ps = g.parts
    i = 0
    while i < len(ps):
        p = ps[i]
        p[1] += p[3]
        p[2] += p[4]
        p[5] -= 1
        if p[0] == 2:
            p[4] += 0.25
        if p[5] <= 0:
            ps.pop(i)
            continue
        x, y, k = int(p[1]), int(p[2]), p[0]
        if k == 0:
            heart(C, x, y, p[6])
        elif k == 1:
            note(C, x, y, p[6])
        elif k == 2:
            drop(C, x, y)
        else:
            C.setTextColor(p[6])
            C.setTextSize(1 if p[5] > 22 else 2)
            C.drawString("z", x, y)
            C.setTextSize(1)
        i += 1


def bubble(C, g):
    b = g.bub
    if not b:
        return
    x = min(W - 30, g.hx + 20)
    y = max(1, g.hy - 24)
    C.fillRoundRect(x, y, 28, 17, 6, CR)
    C.fillCircle(x + 2, y + 19, 2, CR)
    C.fillCircle(x - 2, y + 23, 1, CR)
    if b == "fish":
        fish(C, x + 5, y + 4, FC, 0)
    else:
        C.setTextColor(RD if b in ("!", "?") else BK)
        C.drawString(b, x + 14 - C.textWidth(b) // 2, y + 4)


def fish_step(C, g):
    fs = g.fish
    if fs is None:
        if g.fq:
            g.fq -= 1
            g.fish = [g.hx - 9, -12, 1, 0]
        return
    if fs[3]:
        fs[0] += 3
        fs[1] += fs[2]
        fs[2] += 1
        if fs[1] > PH:
            g.fish = None
            return
    else:
        fs[0] += (g.hx - 9 - fs[0]) // 3
        fs[1] += fs[2]
        if fs[2] < 7:
            fs[2] += 1
        if fs[1] >= g.hy - 6:
            if g.f >= 96:
                fs[3], fs[2] = 1, -6
                g.bub, g.bub_t = "full", 35
                play(g, FULL, True)
            else:
                g.fish = None
                g.eat_t = 16
                g.f = cap(g.f + 12)
                g.j = cap(g.j + 2)
                g.bub, g.bub_t = "yum", 25
                spawn(g, 0, g.hx, g.hy - 6, 0, -1, 24, PK)
                play(g, NOM, True)
                return
    fish(C, fs[0], fs[1], FC, 0)


# Weather kinds, from Open-Meteo's WMO weather codes.
CLEAR, PARTLY, OVERCAST, FOG, RAIN, SNOW, STORM = range(7)
RAYS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def wkind(c):
    if c >= 95:
        return STORM
    if 71 <= c <= 77 or c in (85, 86):
        return SNOW
    if c >= 51:
        return RAIN
    if c >= 45:
        return FOG
    return OVERCAST if c == 3 else PARTLY if c else CLEAR


def sky_color(h, g, f):
    if g.wk == STORM and f % 80 < 3:
        return 0xFFFFFF   # lightning
    night = h < 6 or h >= 20
    if g.wk >= OVERCAST:
        return 0x1C1F2B if night else 0x8D99AE
    return (0x0B1233 if h < 5 or h >= 21 else 0x4B3F72 if h < 7 else 0xF4A261 if h < 9
            else 0x7EC8E3 if h < 17 else 0xE76F51 if h < 19 else 0x3D2C6B)


def clouds(C, g, h, x0, y0, w, n, f, r):
    if g.wk not in (PARTLY, OVERCAST, RAIN, SNOW, STORM):
        return
    col = 0x4A4F60 if h < 6 or h >= 20 else 0xF5F5F5 if g.wk == PARTLY else 0xB0B7C3
    span = w - 2 * r
    for i in range(n if g.wk == PARTLY else n * 2):
        cx = x0 + r + (i * span // n + f // 8) % span
        cy = y0 + r + (i * 5) % (r + 1)
        C.fillEllipse(cx, cy, r, r * 2 // 3, col)
        C.fillCircle(cx - r // 3, cy - r // 3, r // 2, col)


def precip(C, g, x0, y0, w, h, f, n):
    k = g.wk
    if k in (RAIN, STORM):
        for i in range(n):
            C.fillRect(x0 + (i * 37 + f) % w, y0 + (i * 23 + f * 4) % (h - 4), 1, 4, 0x9AD1F5)
    elif k == SNOW:
        for i in range(n):
            C.fillRect(x0 + (i * 31 + f // 3 + (f // 8 + i) % 3) % (w - 1), y0 + (i * 17 + f) % (h - 2),
                       2, 2, 0xFFFFFF)
    elif k == FOG:
        for i in range(0, h - 2, 6):
            C.fillRect(x0, y0 + i + (f // 10) % 3, w, 2, 0xB8BEC8)


def outdoor(C, g, m, ground, f):
    h = m / 60
    g.wall = sky = sky_color(h, g, f)
    C.fillRect(0, 0, W, FLOOR, sky)
    if g.wk < OVERCAST and 6 <= h < 20:
        C.fillCircle(24 + int((h - 6) * 190 / 14), 44 - int(34 * (1 - abs(h - 13) / 7)), 8, YL)
    elif g.wk < OVERCAST:
        for sx, sy in ((20, 10), (70, 30), (130, 8), (180, 24), (220, 12)):
            C.fillRect(sx, sy, 1, 1, CR)
        C.fillCircle(200, 18, 7, 0xF1FAEE)
        C.fillCircle(203, 15, 6, sky)
    clouds(C, g, h, 0, 2, W, 4, f, 14)
    C.fillRect(0, FLOOR, W, PH - FLOOR, ground)


def room(C, g, m, f):
    g.wall = 0x161B28 if m < 420 or m >= 1320 else 0x283040
    C.fillRect(0, 0, W, FLOOR, g.wall)
    C.fillRect(0, FLOOR, W, PH - FLOOR, WD2)
    C.fillRect(0, FLOOR, W, 1, WD)
    h = m / 60
    sky = sky_color(h, g, f)
    C.fillRect(8, 4, 52, 36, 0x5C4033)
    C.fillRect(11, 7, 46, 30, sky)
    if g.wk < OVERCAST and 6 <= h < 20:
        C.fillCircle(16 + int((h - 6) * 36 / 14), 32 - int(20 * (1 - abs(h - 13) / 7)), 4, YL)
    elif g.wk < OVERCAST:
        for sx, sy in ((16, 12), (26, 28), (52, 31), (21, 19)):
            C.fillRect(sx, sy, 1, 1, CR)
        C.fillCircle(44, 16, 5, 0xF1FAEE)
        C.fillCircle(46, 14, 4, sky)
    clouds(C, g, h, 11, 7, 46, 2, f, 6)
    precip(C, g, 11, 7, 46, 30, f, 8)
    C.fillRect(33, 7, 2, 30, 0x5C4033)
    C.fillRect(11, 21, 46, 2, 0x5C4033)
    decor(C, g, m, f)


def decor(C, g, m, f):
    hol = g.hol
    if hol == "xmas":
        for i in range(7):
            C.fillCircle(12 + i * 7, 5, 2, (RD, GN, YL, FC)[(i + f // 8) % 4])
    elif hol == "halloween":
        C.fillEllipse(22, 35, 8, 6, 0xF77F00)
        C.fillRect(21, 28, 2, 3, GN)
        C.fillTriangle(17, 34, 21, 34, 19, 31, BK)
        C.fillTriangle(23, 34, 27, 34, 25, 31, BK)
        C.fillRect(18, 37, 9, 1, BK)
    elif hol == "easter":
        C.fillEllipse(22, 34, 5, 7, 0xBDE0FE)
        C.fillRect(17, 33, 11, 2, PK)
        C.fillEllipse(34, 36, 4, 5, 0xFFC8DD)
    elif hol == "valentine":
        heart(C, 22, 14, PK)
        heart(C, 46, 26, PK)
    elif hol in ("newyear", "bonfire") and (m >= 1020 or m < 360):
        n = f // 24
        cx, cy, r = 20 + (n * 13) % 28, 14 + (n * 7) % 11, (f % 24) // 3
        for dx, dy in RAYS:
            C.fillRect(cx + dx * r, cy + dy * r, 1, 1, (YL, PK, FC, GN)[n % 4])


def hat(C, hol, x, y):
    if hol == "xmas":
        C.fillTriangle(x + 18, y + 1, x + 54, y + 1, x + 48, y - 14, RD)
        C.fillRect(x + 16, y - 2, 40, 4, 0xFFFFFF)
        C.fillCircle(x + 49, y - 15, 3, 0xFFFFFF)
    elif hol == "halloween":
        C.fillTriangle(x + 22, y - 2, x + 50, y - 2, x + 40, y - 20, 0x2B2D42)
        C.fillRect(x + 10, y - 2, 52, 3, 0x2B2D42)
        C.fillRect(x + 25, y - 6, 22, 2, 0x7B2CBF)
    elif hol == "newyear":
        C.fillTriangle(x + 26, y + 1, x + 46, y + 1, x + 36, y - 18, 0xF72585)
        C.fillRect(x + 30, y - 6, 12, 2, YL)
        C.fillRect(x + 33, y - 12, 6, 2, YL)
        C.fillCircle(x + 36, y - 19, 3, YL)
    elif hol == "easter":
        for ex in (x + 26, x + 46):
            C.fillEllipse(ex, y - 10, 4, 10, 0xFFFFFF)
            C.fillEllipse(ex, y - 10, 2, 7, 0xFFC8DD)
    elif hol == "valentine":
        heart(C, x + 36, y - 7, PK)
    elif hol == "bonfire":
        C.fillRoundRect(x + 14, y - 6, 44, 9, 4, 0x2A9D8F)
        C.fillRect(x + 14, y, 44, 3, 0x264653)
        C.fillCircle(x + 36, y - 7, 3, CR)


def bed(C):
    C.fillRect(26, 54, 6, 32, WD)
    C.fillRect(148, 66, 5, 20, WD)
    C.fillRect(32, 70, 116, 9, 0xE8E2D0)
    C.fillRect(32, 79, 116, 4, WD2)


def nightstand(C, lamp):
    if lamp:
        C.fillTriangle(176, 50, 150, 86, 202, 86, 0x3A3626)
    C.fillRect(162, 66, 28, 20, WD)
    C.fillRect(165, 72, 22, 1, WD2)
    C.fillRect(174, 54, 4, 12, MET)
    C.fillRect(168, 44, 16, 10, YL if lamp else 0x7A7A7A)


def sc_sleep(C, g, f):
    nightstand(C, 0)
    bed(C)
    br = (f // 30) % 2
    x = HOME[SLEEP] + (4 if g.ev == "roll" and g.ev_t > 10 else 0)
    awake = g.eat_t or g.wake
    cl(C, g, x, SY + br, "c" if awake else "x", "up" if g.eat_t else "side")
    C.fillRect(40, 62 + br, 108, 18, BL)
    C.fillRect(40, 62 + br, 108, 3, BL2)
    C.fillRect(32, 80, 116, FLOOR - 78, WD2)   # bed base down to the floor, hiding his legs
    C.fillRect(32, FLOOR, 116, 1, WD)
    if not awake and f % 36 == 0:
        spawn(g, 3, x + 62, SY - 4, 0.4, -0.6, 44, CR)


def sc_read(C, g, f):
    nightstand(C, 1)
    bed(C)
    yawn = g.ev == "yawn"
    eyes = "x" if yawn or g.happy or f % 60 < 2 else "c"
    cl(C, g, HOME[READ], SY - 14, "c" if g.eat_t else eyes, "up" if yawn or g.eat_t else "side")
    C.fillRect(62, 64, 86, 16, BL)
    C.fillRect(62, 64, 86, 3, BL2)
    if not yawn:
        C.fillRect(94, 50, 30, 16, 0x9B2D30)
        C.fillRect(96, 52, 12, 12, CR)
        C.fillRect(110, 52, 12, 12, CR)
        for i in range(3):
            C.fillRect(98, 54 + i * 3, 8, 1, GR)
            C.fillRect(112, 54 + i * 3, 8, 1, GR)
        if g.ev == "page":
            C.fillRect(122 - (DUR["page"] - g.ev_t) * 2, 51, 3, 14, 0xFFFFFF)


def sc_coffee(C, g, f, m):
    C.fillRect(150, 64, 48, 4, WD)
    C.fillRect(171, 68, 6, 18, WD2)
    C.fillRect(162, 84, 24, 2, WD2)
    if m < 720:
        C.fillRect(154, 59, 24, 5, 0xCCCCCC)
        C.fillRect(156, 60, 20, 1, GR)
        C.fillRect(156, 62, 14, 1, GR)
    else:
        C.fillEllipse(182, 63, 10, 2, CR)
        C.fillCircle(182, 59, 4, 0xC68B59)
        C.fillRect(180, 57, 1, 1, WD2)
        C.fillRect(183, 60, 1, 1, WD2)
    home = g.x == g.tx and not g.ev
    ph = f % 110
    sip = home and ph < 26 and not g.eat_t
    if home and ph == 26:
        g.jit = 14
    dx = (1 if f % 2 else -1) if g.jit else 0
    auto(C, g, f, "mug" if sip else "side", None, dx)
    x, y = g.x + dx, SY + g.jy
    mx, my = (x + 56, y - 2) if sip else (x + 66, y + 12)
    C.fillRect(mx, my, 8, 10, CR)
    C.fillRect(mx + 1, my + 1, 6, 2, 0x6F4E37)
    C.fillRect(mx + 8, my + 3, 2, 4, CR)
    if not sip:
        for i in range(3):
            C.fillRect(mx + 2 + ((f // 5 + i) % 2) * 2, my - 4 - i * 4, 1, 3, 0x9A9A9A)


def sc_work(C, g, f):
    C.fillRect(120, 64, 106, 4, WD)
    C.fillRect(124, 68, 4, 18, WD2)
    C.fillRect(218, 68, 4, 18, WD2)
    C.fillRect(168, 56, 8, 8, MET)
    C.fillRect(160, 62, 24, 2, MET)
    C.fillRect(134, 16, 76, 42, 0x3A3A3A)
    C.fillRect(137, 19, 70, 36, 0x0D1117)
    C.fillRect(128, 61, 28, 3, 0xBBBBBB)
    C.fillRect(200, 56, 8, 8, CR)
    C.fillRect(201, 57, 6, 2, 0x6F4E37)
    ev = g.ev
    busy = g.x == g.tx and ev in (None, "think", "bug", "idea", "ship")
    if ev == "think":
        C.setTextColor(OR)
        C.drawString("* thinking" + "." * ((f // 8) % 4), 141, 32)
    elif ev == "ship":
        C.fillRect(137, 19, 70, 36, 0x0F3D1F)
        C.setTextColor(GN)
        C.drawString("tests pass!", 143, 32)
    else:
        if busy and f % 5 == 0:
            g.lines.pop(0)
            g.lines.append([rnd(3) * 5, 8 + rnd(40), CODE[rnd(6)]])
        for i, ln in enumerate(g.lines):
            C.fillRect(141 + ln[0], 22 + i * 5, ln[1], 3, RD if ev == "bug" and i == 3 else ln[2])
        if f % 16 < 8:
            C.fillRect(141, 52, 4, 2, OR)
    arms = "side"
    if busy and ev in (None, "bug"):
        arms = "down" if (f // 3) % 2 else "side"
    if ev == "ship":
        arms = "up"
    if ev == "bug" and f % 20 == 0:
        spawn(g, 2, g.x + 60, SY - 2, 0.5, -1.5, 20)
    auto(C, g, f, arms, "r" if busy else None)


def sc_eat(C, g, f, m):
    C.fillRect(110, 66, 88, 4, WD)
    C.fillRect(114, 70, 4, 16, WD2)
    C.fillRect(190, 70, 4, 16, WD2)
    if m >= 1140:
        C.fillRect(182, 52, 4, 14, CR)
        C.fillTriangle(181, 52, 187, 52, 184, 45 - (f // 4) % 2, YL if f % 6 < 3 else OR)
    else:
        C.fillRect(178, 54, 8, 12, 0xBFE3F7)
        C.fillRect(179, 58, 6, 7, 0x7FC4EC)
    home = g.x == g.tx and not g.ev
    if g.bite < 4:
        fish(C, 130, 54, 0x8FB3C9, 1)
        if g.bite:
            C.fillRect(129, 53, g.bite * 4 + 1, 10, g.wall)
    else:
        C.fillRect(132, 58, 16, 1, CR)
        for i in range(4):
            C.fillRect(134 + i * 4, 56, 1, 5, CR)
        C.fillCircle(130, 58, 2, CR)
        if home:
            g.meal_t += 1
            if g.meal_t > 60:
                g.bite = g.meal_t = 0
    C.fillEllipse(142, 65, 20, 3, CR)
    lean, arms = 0, "side"
    if home and g.bite < 4:
        ph = f % 70
        if ph < 10:
            lean, arms = 8, "down"
        if ph == 9:
            g.bite += 1
    auto(C, g, f, arms, "r" if home else None, lean)


def sc_gym(C, g, f):
    C.fillRect(30, 84, 180, 3, 0x2E7D32)
    if g.sub_t <= 0:
        g.sub = (g.sub + 1) % 3
        g.sub_t = 260
        g.tx, g.spd = HOME[GYM], 1
    g.sub_t -= 1
    arms = "side"
    if g.sub == 0:
        if g.x == g.tx:
            arms = "up" if (f // 14) % 2 else "side"
    elif g.sub == 1:
        if g.x == g.tx and not g.jy and not g.vy:
            g.vy = -5
        arms = "up" if g.jy < -3 else "side"
    else:
        g.spd = 3
        if g.x == g.tx:
            g.tx = 8 if g.x > 100 else 160
    if f % 30 == 0:
        spawn(g, 2, g.x + (8 if f % 60 else 64), SY + g.jy, -0.6 if f % 60 else 0.6, -1.6, 22)
    auto(C, g, f, arms)
    x, y = g.x, SY + g.jy
    C.fillRect(x + 12, y + 2, 48, 3, RD)
    if g.sub == 0:
        if arms == "up" and not g.eat_t:
            bell(C, x + 6, y - 3)
            bell(C, x + 66, y - 3)
        else:
            bell(C, x + 4, y + 20)
            bell(C, x + 68, y + 20)


def sc_tv(C, g, f):
    C.fillRect(186, 74, 20, 12, MET)
    C.fillRect(160, 34, 70, 42, 0x222222)
    if f % 8 == 0:
        g.tvs = rnd(30000) + 1
    s = g.tvs
    C.fillRect(163, 37, 64, 36, (0x264653, 0x2A9D8F, 0x8AB17D, 0xE9C46A)[s % 4])
    for _ in range(3):
        s = (s * 75 + 74) % 65537
        C.fillRect(163 + s % 48, 37 + (s >> 4) % 26, 8 + s % 10, 6 + s % 6, (OR, CR, PK, YL, GN, FC)[s % 6])
    C.fillRect(24, 46, 100, 26, 0x2A6F77)
    laugh = g.ev == "laugh"
    y = SY - 8 - (2 if laugh and (f // 3) % 2 else 0)
    arms = "up" if laugh or g.happy or g.eat_t else ("mug" if g.ev == "popcorn" else "side")
    if g.eat_t:
        eyes = "x" if (g.eat_t // 3) % 2 else "c"
    elif laugh or g.happy or f % 55 < 2:
        eyes = "x"
    elif g.ev == "look":
        eyes = "lcr"[(g.ev_t // 12) % 3]
    else:
        eyes = "r"
    cl(C, g, HOME[TV], y, eyes, arms)
    C.fillRect(24, 70, 100, 12, 0x22595F)
    C.fillRect(18, 56, 12, 26, 0x1E4F55)
    C.fillRect(118, 56, 12, 26, 0x1E4F55)
    C.fillRect(24, 82, 4, 4, WD2)
    C.fillRect(120, 82, 4, 4, WD2)
    C.fillRect(80, 62, 22, 8, RD)
    C.fillRect(84, 62, 3, 8, CR)
    C.fillRect(92, 62, 3, 8, CR)
    for px in (82, 87, 92, 97):
        C.fillCircle(px, 61, 2, POP)
    if g.ev == "popcorn":
        C.fillCircle(HOME[TV] + 66, y - 3, 2, POP)


def sc_play(C, g, f, mode=None):
    # mode None alternates dancing (0) and acrobatics (1) every ~22 s; otherwise stays on mode.
    if mode is not None and g.sub != mode:
        g.sub, g.sub_t = mode - 1, 0
    if g.sub_t <= 0:
        g.sub = (g.sub + 1) % 2
        g.sub_t = 300 if mode is None else 1000000
        g.tx, g.spd, g.cart = HOME[PLAY], 1, 0
        if g.sub == 0:
            play(g, DANCE_TUNE)
    g.sub_t -= 1
    if g.sub == 0:
        for i in range(8):
            C.fillRect(i * 30, FLOOR + 1, 30, PH - FLOOR - 1,
                       (0x7B2CBF, 0xF72585, 0x4CC9F0, 0xFFD60A)[(i + f // 6) % 4])
        C.fillRect(119, 0, 2, 6, GR)
        C.fillCircle(120, 12, 7, 0xC0C0C0)
        for i in range(3):
            C.fillRect(114 + (f * 3 + i * 5) % 12, 7 + i * 4, 2, 2, 0xFFFFFF)
        if g.x == g.tx:
            g.tx = 70 if g.x > 84 else 98
            if not g.jy:
                g.vy = -4
        if f % 14 == 0:
            spawn(g, 1, 20 + rnd(200), 60, 0, -1, 40, (YL, PK, GN, FC)[rnd(4)])
        auto(C, g, f, "up" if (f // 10) % 2 else "side", "c")
        return
    if g.cart:
        g.cart -= 1
        rot = ((16 - g.cart) // 4) % 4
        if g.dir < 0:
            rot = (4 - rot) % 4
        g.x = max(4, min(W - 76, g.x + 3 * g.dir))
        g.tx = g.x
        if rot % 2:
            cl(C, g, g.x + 16, FLOOR - 72, "c", "side", 0, rot)
        else:
            cl(C, g, g.x, SY, "c", "side", 0, rot)
        return
    if g.x == g.tx and not g.jy and f % (16 if mode else 40) == 0:
        r = rnd(4)
        if r == 0:
            g.tx = 4 + rnd(W - 80)
        elif r == 1 and not mode:
            g.vy = -7
        elif r >= 1:
            g.cart = 16
            g.dir = 1 if g.x < 100 else -1
    auto(C, g, f)


def wheel(C, cx, cy, f):
    C.fillCircle(cx, cy, 10, 0x222222)
    C.fillCircle(cx, cy, 8, 0xBBBBBB)
    if (f // 2) % 2:
        C.fillRect(cx - 7, cy, 15, 1, MET)
        C.fillRect(cx, cy - 7, 1, 15, MET)
    else:
        C.drawLine(cx - 5, cy - 5, cx + 5, cy + 5, MET)
        C.drawLine(cx - 5, cy + 5, cx + 5, cy - 5, MET)
    C.fillCircle(cx, cy, 2, MET)


def sc_bike(C, g, f, m, commute):
    outdoor(C, g, m, 0, f)
    off = f * 3
    if commute:
        for i in range(6):
            bx = (i * 48 - off // 2) % 288 - 48
            bh = 22 + (i * 37) % 34
            C.fillRect(bx, FLOOR - bh, 40, bh, (0x3D405B, 0x4A4E69, 0x22223B)[i % 3])
            for wy in range(FLOOR - bh + 5, FLOOR - 6, 9):
                C.fillRect(bx + 6, wy, 5, 4, YL if (i + wy) % 3 else 0x8D99AE)
                C.fillRect(bx + 26, wy, 5, 4, 0x8D99AE if (i + wy) % 2 else YL)
    else:
        for i in range(3):
            C.fillCircle((i * 130 - off // 4) % 390 - 70, FLOOR + 34, 62, 0x88B04B)
        for i in range(4):
            tx = (i * 70 - off // 2) % 280 - 20
            C.fillRect(tx + 6, FLOOR - 16, 4, 16, WD2)
            C.fillCircle(tx + 8, FLOOR - 22, 10, 0x2D6A4F)
    C.fillRect(0, FLOOR, W, PH - FLOOR, 0x555555 if commute else 0xA98467)
    C.fillRect(0, FLOOR, W, 1, 0x333333)
    for i in range(6):
        C.fillRect((i * 48 - off) % 288 - 48, FLOOR + 5, 20, 2, CR)
    x = HOME[BIKE]
    y = SY - 12 + (f // 3) % 2
    frame = FC if commute else RD
    if commute:
        C.fillRect(x - 2, y + 6, 12, 18, 0x6D597A)
    wheel(C, x + 10, FLOOR - 10, f)
    wheel(C, x + 62, FLOOR - 10, f)
    for d in (0, 1):
        C.drawLine(x + 10, FLOOR - 10 + d, x + 36, FLOOR - 12 + d, frame)
        C.drawLine(x + 36, FLOOR - 12 + d, x + 62, FLOOR - 10 + d, frame)
        C.drawLine(x + 36 + d, FLOOR - 12, x + 30 + d, FLOOR - 26, frame)
        C.drawLine(x + 30, FLOOR - 26 + d, x + 58, FLOOR - 28 + d, frame)
        C.drawLine(x + 58 + d, FLOOR - 28, x + 62 + d, FLOOR - 10, frame)
    eyes = "x" if f % 50 < 2 else "r"
    if g.eat_t:
        eyes = "x" if (g.eat_t // 3) % 2 else "c"
    cl(C, g, x, y, eyes, "up" if g.happy or g.eat_t else "side", (f // 3) % 2)
    if commute:
        C.fillRoundRect(x + 14, y - 5, 44, 8, 4, RD)
    elif f % 160 == 0:
        g.bub, g.bub_t = "wee!", 30


def sc_volley(C, g, f, m):
    outdoor(C, g, m, 0xE9D8A6, f)
    C.fillRect(0, FLOOR - 10, W, 10, 0x219EBC)
    for i in range(5):
        C.fillRect((i * 56 + f) % 280 - 20, FLOOR - 7 + (i % 2) * 3, 10, 1, CR)
    C.fillRect(119, FLOOR - 46, 2, 46, CR)
    for i in range(6):
        C.fillRect(116, FLOOR - 46 + i * 4, 8, 1, CR)
    C.fillRect(116, FLOOR - 46, 1, 21, CR)
    C.fillRect(123, FLOOR - 46, 1, 21, CR)
    if g.ball is None:
        g.ball = [60.0, 40.0, 4.0, -3.8, 0]   # x, y, vx, vy, frames resting after a point
        g.score = [0, 0]
        g.ojy = g.ovy = 0
    b = g.ball
    if b[4]:
        b[4] -= 1
        if not b[4]:
            left = b[0] < 120
            b[:4] = [60.0 if left else 180.0, 40.0, 4.0 if left else -4.0, -3.8]
    else:
        b[3] += 0.25
        b[0] += b[2]
        b[1] += b[3]
        if b[1] >= FLOOR - 4:
            b[1] = FLOOR - 4.0
            b[4] = 40
            mine = b[0] > 120
            g.score[0 if mine else 1] += 1
            g.bub, g.bub_t = ("yes!", 35) if mine else ("oops", 35)
        elif b[2] < 0 and b[0] <= 60 and b[1] > 20:
            if rnd(7):
                b[2], b[3] = 3.6 + rnd(9) / 10, -3.8
                if not g.jy:
                    g.vy = -5
        elif b[2] > 0 and b[0] >= 180 and b[1] > 20:
            if rnd(7):
                b[2], b[3] = -3.6 - rnd(9) / 10, -3.8
                if not g.ojy:
                    g.ovy = -5
    if g.ovy or g.ojy:
        g.ojy += g.ovy
        g.ovy += 1
        if g.ojy >= 0:
            g.ojy = g.ovy = 0
    s = "%d : %d" % (g.score[0], g.score[1])
    tw = C.textWidth(s)
    C.fillRoundRect(116 - tw // 2, 1, tw + 8, 12, 4, DK)   # readable over the sun or any sky
    C.setTextColor(CR)
    C.drawString(s, 120 - tw // 2, 2)
    cl(C, g, 144, SY + g.ojy, "l" if f % 50 > 1 else "x", "up" if g.ojy else "side",
       (f // 4) % 2 if g.ojy else 0, 0, FC)
    eyes = "x" if f % 50 < 2 else ("l" if b[0] < 96 else "r")
    if g.eat_t:
        eyes = "x" if (g.eat_t // 3) % 2 else "c"
    cl(C, g, HOME[VOLLEY], SY + g.jy, eyes, "up" if g.jy or g.happy or g.eat_t else "side",
       (f // 4) % 2 if g.jy else 0)
    bx, by = int(b[0]), int(b[1])
    C.fillCircle(bx, by, 4, 0xFFFFFF)
    C.fillRect(bx - 4, by, 9, 1, YL)


def sc_yoga(C, g, f):
    C.fillRect(46, FLOOR - 2, 148, 3, 0x9D4EDD)
    C.fillRect(196, FLOOR - 18, 10, 18, 0xC68B59)
    C.fillCircle(201, FLOOR - 24, 8, 0x52B788)
    ph = (f // 50) % 4
    x = HOME[YOGA]
    if g.eat_t or g.happy:
        cl(C, g, x, SY, "x" if (g.eat_t // 3) % 2 else "c", "up")
    elif ph == 0:
        cl(C, g, x, SY, "x", "up")
    elif ph == 1:
        cl(C, g, x, SY + 6, "x", "down")
    elif ph == 2:
        cl(C, g, x, SY, "c", "side", 0, 2)
    else:
        cl(C, g, x, SY + (f // 25) % 2, "x", "side")
    if f % 120 == 60:
        g.bub, g.bub_t = "om", 40


def sc_music(C, g, f):
    C.fillRect(150, 62, 56, 24, WD)
    C.fillRect(152, 66, 52, 1, WD2)
    C.fillRect(152, 57, 52, 5, DK)
    C.fillEllipse(176, 57, 18, 3, BK)
    C.fillEllipse(176, 57, 5, 1, RD)
    a = (f // 2) % 4
    C.fillRect(176 + (12, 0, -12, 0)[a], 57 + (0, -2, 0, 2)[a], 2, 1, 0x555555)
    C.drawLine(200, 50, 186, 57, GR)
    C.fillRect(199, 48, 4, 4, GR)
    C.fillRect(212, 46, 22, 40, DK)
    C.fillCircle(223, 58, 7, MET)
    C.fillCircle(223, 58, 3 + (f // 4) % 2, BK)
    C.fillCircle(223, 76, 4, MET)
    x = HOME[MUSIC]
    beat = (f // 6) % 2
    y = SY - 4 + beat * 2
    if g.eat_t:
        eyes, arms = ("x" if (g.eat_t // 3) % 2 else "c"), "up"
    else:
        eyes = "x" if (f // 40) % 2 else "c"
        arms = "up" if g.happy or (f // 80) % 4 == 3 else "side"
    cl(C, g, x, y, eyes, arms, beat)
    C.fillRect(x + 12, y - 3, 48, 3, DK)
    C.fillRect(x + 10, y - 1, 3, 8, DK)
    C.fillRect(x + 59, y - 1, 3, 8, DK)
    C.fillRoundRect(x + 6, y + 4, 8, 10, 3, RD)
    C.fillRoundRect(x + 58, y + 4, 8, 10, 3, RD)
    C.fillEllipse(x + 36, FLOOR - 5, 46, 10, 0x7B2CBF)
    C.fillEllipse(x + 30, FLOOR - 9, 20, 3, 0x9D4EDD)
    if f % 12 == 0:
        spawn(g, 1, 212 + rnd(20), 44, -0.6, -0.8, 50, (YL, PK, GN, FC)[rnd(4)])


class G:
    def __init__(self):
        self.x = self.tx = HOME[COFFEE]
        self.dir, self.spd, self.jy, self.vy, self.cart = 1, 1, 0, 0, 0
        self.scene, self.ev, self.ev_t, self.next_ev = -1, None, 0, 200
        self.sub, self.sub_t, self.bite, self.meal_t = -1, 0, 0, 0
        self.parts, self.bub, self.bub_t = [], None, 0
        self.fish, self.fq, self.eat_t, self.happy, self.wake, self.jit = None, 0, 0, 0, 0, 0
        self.f, self.e, self.j, self.s = 70.0, 80.0, 70.0, 60.0
        self.sim, self.buf, self.buf_t = None, "", 0
        self.mute, self.snd, self.snd_t, self.snd_on = False, [], 0, False
        self.need, self.song = 0.2, 0
        self.lines = [[rnd(3) * 5, 8 + rnd(40), CODE[rnd(6)]] for _ in range(6)]
        self.wall, self.tvs, self.hx, self.hy, self.br = 0x283040, 1, 0, 0, 100
        self.hk = self.fk = None
        self.side, self.side_end, self.cool = None, 0, time.ticks_ms()
        self.ball, self.score, self.ojy, self.ovy = None, [0, 0], 0, 0
        self.hol, self.help, self.temp, self.hum, self.wk = None, 0, None, None, CLEAR
        self.net_t, self.next_net, self.next_ntp, self.res = None, 0, 0, None
        self.bat, self.chg = None, False


def play(g, notes, reply=False):
    # Replies to your keys always sound; Clawd's own noises stay quiet while he sleeps.
    if not g.mute and (reply or g.scene != SLEEP):
        g.snd = list(notes)
        g.snd_t = time.ticks_ms()


def sound(g):
    now = time.ticks_ms()
    if time.ticks_diff(now, g.snd_t) < 0:
        return
    if g.snd:
        fq, d = g.snd.pop(0)
        if fq:
            try:
                M5.Speaker.tone(fq, d)
            except Exception:
                pass
        g.snd_t = time.ticks_add(now, d + 25)
        g.snd_on = True
    elif g.snd_on:
        # Explicit stop once a tune ends, so a tone can never be left buzzing.
        try:
            M5.Speaker.stop()
        except Exception:
            pass
        g.snd_on = False


def clock_ok():
    return time.localtime()[0] >= 2025


def uk_off(t):
    # BST runs from the last Sunday of March to the last Sunday of October, 01:00 UTC.
    y = time.localtime(t)[0]
    a = time.mktime((y, 3, 31 - (5 * y // 4 + 4) % 7, 1, 0, 0, 0, 0))
    b = time.mktime((y, 10, 31 - (5 * y // 4 + 1) % 7, 1, 0, 0, 0, 0))
    return 3600 if a <= t < b else 0


def live_secs():
    if clock_ok():
        t = time.time()
        return (t + uk_off(t)) % 86400
    return (43200 + time.ticks_ms() // 1000) % 86400


def minutes(g):
    s = live_secs()
    if g.sim is not None:
        s = (s + g.sim) % 86400
    return s // 60


def scene_at(m):
    for end, sc in SCHED:
        if m < end:
            return sc
    return SLEEP


def easter(y):
    # Anonymous Gregorian algorithm; returns (month, day) of Easter Sunday.
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    n = h + l - 7 * ((a + 11 * h + 22 * l) // 451) + 114
    return n // 31, n % 31 + 1


def holiday():
    if not clock_ok():
        return None
    t = time.time()
    y, mo, d = time.localtime(t + uk_off(t))[:3]
    md = mo * 100 + d
    if md in (1231, 101):
        return "newyear"
    if md == 214:
        return "valentine"
    if md == 1031:
        return "halloween"
    if md == 1105:
        return "bonfire"
    if 1224 <= md <= 1226:
        return "xmas"
    em, ed = easter(y)
    days = (time.mktime((y, mo, d, 12, 0, 0, 0, 0)) - time.mktime((y, em, ed, 12, 0, 0, 0, 0))) // 86400
    return "easter" if -2 <= days <= 1 else None   # Good Friday to Easter Monday


def start_ev(g, e):
    g.ev, g.ev_t = e, DUR[e]
    if e == "wander":
        g.tx = 4 + rnd(W - 80)
    elif e == "hop":
        g.vy = -6
    elif e == "ship":
        g.vy = -6
        g.j = cap(g.j + 3)
        play(g, JINGLE)
    elif e in BUBBLES:
        g.bub, g.bub_t = BUBBLES[e], DUR[e]


def set_side(g, s):
    now = time.ticks_ms()
    g.side = s
    g.side_end = time.ticks_add(now, SIDE_MS)
    g.cool = time.ticks_add(now, SIDE_MS + 1800000)


def update(g, m):
    if g.side is not None and time.ticks_diff(time.ticks_ms(), g.side_end) >= 0:
        g.side = None
    sc = scene_at(m) if g.side is None else g.side
    if sc != g.scene:
        was = g.scene
        g.scene, g.ev, g.next_ev = sc, None, 120
        g.sub, g.sub_t, g.cart, g.spd, g.ball = -1, 0, 0, 1, None
        g.tx = HOME[sc]
        if sc in FIXED:
            g.x = g.tx
            g.jy = g.vy = 0
        if was == SLEEP:
            play(g, WAKE)
            if sc not in FIXED:
                g.vy = -6
        if sc == MUSIC:
            play(g, MUSIC_TUNE)
        try:
            L.setBrightness(30 if sc == SLEEP else g.br)
        except Exception:
            pass
    if g.vy or g.jy:
        g.jy += g.vy
        g.vy += 1
        if g.jy >= 0:
            g.jy = g.vy = 0
    if g.x != g.tx and not g.cart:
        g.dir = 1 if g.tx > g.x else -1
        g.x += min(g.spd, abs(g.tx - g.x)) * g.dir
    if g.ev:
        g.ev_t -= 1
        if g.ev_t <= 0:
            if g.ev == "wander":
                g.tx = HOME[sc]
            g.ev = None
    elif g.x == g.tx and EVENTS[sc]:
        g.next_ev -= 1
        if g.next_ev <= 0:
            evs = EVENTS[sc]
            start_ev(g, evs[rnd(len(evs))])
            g.next_ev = 220 + rnd(360)
    if g.eat_t:
        g.eat_t -= 1
    if g.happy:
        g.happy -= 1
    if g.wake:
        g.wake -= 1
    if g.jit:
        g.jit -= 1
    if g.bub_t:
        g.bub_t -= 1
        if not g.bub_t:
            g.bub = None


def stats(g, mins, m):
    sc = g.scene
    g.f = cap(g.f + mins * F_RATE[sc])
    g.e = cap(g.e + mins * E_RATE[sc])
    g.j = cap(g.j + mins * J_RATE[sc])
    g.s = cap(g.s + mins * S_RATE[sc])
    g.hol = holiday()
    read_battery(g)
    if g.res is None and g.net_t is None:
        reserve(g, True)
    if sc == SLEEP:
        return
    if g.bat is not None and g.bat < 15 and not g.chg and not g.bub and rnd(40) == 0:
        g.bub, g.bub_t = "low!", 40
    elif g.hol and not g.bub and rnd(60) == 0:
        g.bub, g.bub_t = GREET[g.hol], 40
    # About one spontaneous side activity per 45 minutes awake, at least 30 minutes apart.
    if (g.side is None and scene_at(m) not in (COMMUTE, READ)
            and time.ticks_diff(time.ticks_ms(), g.cool) >= 0 and rnd(int(45 / mins) or 1) == 0):
        set_side(g, SIDES[rnd(len(SIDES))])
    g.need -= mins
    if g.need > 0:
        return
    if g.f < 30:
        g.bub, g.bub_t, g.need = "fish", 50, 0.4
        i = rnd(len(CHIRPS) - 1)
        if i >= g.song:
            i += 1
        g.song = i
        play(g, CHIRPS[i])
    elif g.e < 20:
        g.bub, g.bub_t, g.need = "zz", 40, 1.5
    elif g.j < 20:
        g.bub, g.bub_t, g.need = "...", 40, 2.0
        play(g, SIGH)
    else:
        g.need = 0.2


def pet(g):
    g.j = cap(g.j + 6)
    for i in range(3):
        spawn(g, 0, g.hx - 12 + i * 12, g.hy - 2, 0, -1.0 - i * 0.3, 26, PK)
    play(g, PET, True)
    if g.scene == SLEEP:
        g.wake, g.bub, g.bub_t = 30, "zz?", 30
    elif g.scene not in FIXED and not g.jy and not g.cart:
        g.vy, g.happy = -6, 14
    else:
        g.happy = 20


def key(g, k):
    if isinstance(k, str):
        k = ord(k[0]) if k else 0
    if g.help:   # any key closes the key list
        g.help = 0
        return
    if k in (0x3F, 0x1B, 0x60):   # ? or Esc (Fn+`) or `
        g.help = 200
    elif k in (0x0A, 0x0D):
        if g.buf:
            v = int(g.buf)
            hh, mm = (v, 0) if len(g.buf) <= 2 else (v // 100, v % 100)
            if hh <= 24 and mm < 60:
                g.sim = ((hh % 24) * 3600 + mm * 60 - live_secs()) % 86400
        else:
            g.sim = None
        g.buf = ""
    elif k in (0x08, 0x7F):
        g.buf = g.buf[:-1]
    elif k == 0x09:
        g.mute = not g.mute
    elif 48 <= k <= 57:
        if len(g.buf) < 4:
            g.buf += chr(k)
        g.buf_t = time.ticks_ms()
    elif k == 0x20:
        pet(g)
    elif k in ARROWS:   # , ; . / on their own, or 180-183 with Fn held
        set_side(g, CYCLE[(CYCLE.index(g.side) + ARROWS[k]) % len(CYCLE)])
    elif 65 <= k <= 90 or 97 <= k <= 122:
        if g.fq < 3:
            g.fq += 1


def read_battery(g):
    try:
        g.bat = M5.Power.getBatteryLevel()
        g.chg = bool(M5.Power.isCharging())
    except Exception:
        g.bat = None


def battery(x, y, lvl, chg, blink_off):
    L.drawRect(x, y, 14, 8, GR)
    L.fillRect(x + 14, y + 2, 2, 4, GR)
    if not blink_off:
        L.fillRect(x + 2, y + 2, max(1, lvl * 10 // 100), 4, GN if lvl > 50 else YL if lvl > 20 else RD)
    if chg:
        L.fillTriangle(x + 8, y - 1, x + 4, y + 4, x + 8, y + 4, CR)
        L.fillTriangle(x + 6, y + 3, x + 10, y + 3, x + 6, y + 9, CR)


def hud(g, m, f, force):
    sc = g.scene
    if sc == EAT and m >= 900:
        lab = "dinner"
    elif sc == COMMUTE:
        lab = "biking to work" if m < 720 else "biking home"
    else:
        lab = LABEL[sc]
    if g.side is not None:
        lab += " %dm" % (time.ticks_diff(g.side_end, time.ticks_ms()) // 60000 + 1)
    live = g.sim is None
    ck = "%02d:%02d" % (m // 60, m % 60) if clock_ok() or not live else "--:--"
    low = g.bat is not None and g.bat < 15 and not g.chg
    blink_off = low and (f // 8) % 2
    hk = (lab, ck, live, g.mute, g.temp, g.hum, g.bat, g.chg, blink_off)
    if force or hk != g.hk:
        g.hk = hk
        L.fillRect(0, 0, W, 20, DK)
        L.fillRect(0, 20, W, 1, OR)
        L.setTextColor(OR, DK)
        L.drawString(lab, 6, 5)
        x = W - 4
        if g.bat is not None:
            x -= 16
            battery(x, 6, g.bat, g.chg, blink_off)
            x -= 6
        s = ck if live else "~" + ck
        x -= L.textWidth(s)
        L.setTextColor(CR if live else YL, DK)
        L.drawString(s, x, 5)
        if g.temp is not None:
            t1, t2 = "%d" % round(g.temp), "C %d%%" % g.hum
            x -= 10 + L.textWidth(t1) + 4 + L.textWidth(t2)
            L.setTextColor(0x9AD1F5, DK)
            L.drawString(t1, x, 5)
            L.drawCircle(x + L.textWidth(t1) + 2, 6, 1, 0x9AD1F5)
            L.drawString(t2, x + L.textWidth(t1) + 4, 5)
        if g.mute:
            x -= 20
            L.fillRect(x, 8, 3, 5, GR)
            L.fillTriangle(x + 2, 10, x + 6, 6, x + 6, 15, GR)
            L.drawLine(x + 8, 7, x + 12, 13, RD)
            L.drawLine(x + 8, 13, x + 12, 7, RD)
    if g.buf:
        tip = "> " + g.buf + "_"
    elif live and not clock_ok():
        tip = "clock not set: type an hour + enter"
    else:
        tip = "press ? for keys"
    if force or tip != g.fk:
        g.fk = tip
        L.fillRect(0, H - 17, W, 17, DK)
        L.setTextColor(YL if g.buf else GR, DK)
        L.drawString(tip, (W - L.textWidth(tip)) // 2, H - 13)


def tick(C, g, f):
    m = minutes(g)
    update(g, m)
    sc = g.scene
    if sc in (COMMUTE, BIKE):
        sc_bike(C, g, f, m, sc == COMMUTE)
    elif sc == VOLLEY:
        sc_volley(C, g, f, m)
    else:
        room(C, g, m, f)
        if sc == SLEEP:
            sc_sleep(C, g, f)
        elif sc == COFFEE:
            sc_coffee(C, g, f, m)
        elif sc == WORK:
            sc_work(C, g, f)
        elif sc == EAT:
            sc_eat(C, g, f, m)
        elif sc == GYM:
            sc_gym(C, g, f)
        elif sc == TV:
            sc_tv(C, g, f)
        elif sc == PLAY:
            sc_play(C, g, f)
        elif sc == CART:
            sc_play(C, g, f, 1)
        elif sc == DANCE:
            sc_play(C, g, f, 0)
        elif sc == YOGA:
            sc_yoga(C, g, f)
        elif sc == MUSIC:
            sc_music(C, g, f)
        else:
            sc_read(C, g, f)
    if sc in (COMMUTE, BIKE, VOLLEY):
        precip(C, g, 0, 0, W, FLOOR, f, 26)
    fish_step(C, g)
    particles(C, g)
    bubble(C, g)
    if g.help:
        g.help -= 1
        C.fillRoundRect(6, 3, 228, 91, 6, DK)
        C.drawRoundRect(6, 3, 228, 91, 6, OR)
        for i, (k, d) in enumerate(HELP):
            C.setTextColor(OR)
            C.drawString(k, 14, 9 + i * 12)
            C.setTextColor(CR)
            C.drawString(d, 92, 9 + i * 12)
    return m


def fetch_weather(g):
    # Plain HTTP: HTTPS would need memory this device doesn't have to spare.
    host = "api.open-meteo.com"
    try:
        s = socket.socket()
        s.settimeout(6)
        try:
            s.connect(socket.getaddrinfo(host, 80)[0][-1])
            s.send(("GET /v1/forecast?latitude=%s&longitude=%s&current=temperature_2m,"
                    "relative_humidity_2m,weather_code HTTP/1.0\r\nHost: %s\r\n\r\n"
                    % (LAT, LON, host)).encode())
            data = b""
            while True:
                c = s.recv(512)
                if not c:
                    break
                data += c
        finally:
            s.close()
        cur = json.loads(data.split(b"\r\n\r\n", 1)[1])["current"]
        g.temp, g.hum = cur["temperature_2m"], cur["relative_humidity_2m"]
        g.wk = wkind(cur["weather_code"])
        print("clawd: weather", g.temp, g.hum, g.wk)
        return True
    except Exception as e:
        print("clawd: weather failed:", e)
        return False


RESERVE_SIZES = ((120, 100), (100, 80), (80, 64))   # 24, 16 and 10 KB canvases


def reserve(g, hold):
    # MicroPython's heap grows into free system memory and never gives it back, which
    # would eventually leave WiFi no room to start. An unused buffer keeps that memory
    # claimed between weather checks and is released just before WiFi starts. Right after
    # a fetch the network stack still holds some buffers, so stats() retries every 5 s.
    if hold and g.res is None:
        for w, h in RESERVE_SIZES:
            r = L.newCanvas(w, h, 16, 0)
            if r.width():
                g.res = r
                builtins.clawd_res = w * h * 2
                return
            r.delete()   # a failed canvas leaks ~356 bytes of system memory unless deleted
        builtins.clawd_res = 0
    elif not hold and g.res is not None:
        g.res.delete()
        g.res = None


def sync(g):
    # Blocking, at boot only. WiFi stays off between checks; it holds memory the app needs.
    sta = network.WLAN(network.STA_IF)
    try:
        import clawd_wifi   # imported here so a missing clawd_secrets.py only disables WiFi
        if clawd_wifi.connect(7000):
            fetch_weather(g)
    except Exception as e:
        print("clawd: sync failed:", e)
    sta.active(False)
    now = time.ticks_ms()
    g.next_net = time.ticks_add(now, NET_MS)
    g.next_ntp = time.ticks_add(now, 86400000)


def net_step(g):
    # Hourly weather (and daily clock) refresh. Connecting happens in the background
    # across frames so the animation keeps running; only the fetch itself blocks briefly.
    sta = network.WLAN(network.STA_IF)
    now = time.ticks_ms()
    if g.net_t is None:
        if time.ticks_diff(now, g.next_net) < 0:
            return
        reserve(g, False)
        try:
            import clawd_wifi
            clawd_wifi.begin()
            g.net_t = now
        except Exception as e:
            print("clawd: wifi failed:", e)
            sta.active(False)
            reserve(g, True)
            g.next_net = time.ticks_add(now, 600000)
        return
    connected = sta.isconnected()
    if not connected and time.ticks_diff(now, g.net_t) < 20000:
        return
    import clawd_wifi
    ok = connected and fetch_weather(g)
    if connected:
        if not clock_ok() or time.ticks_diff(now, g.next_ntp) >= 0:
            if clawd_wifi.sync_clock():
                g.next_ntp = time.ticks_add(now, 86400000)
        retry = 600000
    else:
        print("clawd: could not join", clawd_wifi.current())
        clawd_wifi.next_network()   # e.g. moved from home to the office
        retry = 300000
    sta.active(False)
    reserve(g, True)
    g.net_t = None
    g.next_net = time.ticks_add(now, NET_MS if ok else retry)


def load(g):
    try:
        with open(SAVE) as fh:
            g.f, g.e, g.j, g.s = [cap(float(v)) for v in fh.read().split()[:4]]
    except Exception:
        pass


def save(g):
    try:
        with open(SAVE, "w") as fh:
            fh.write("%d %d %d %d" % (int(g.f), int(g.e), int(g.j), int(g.s)))
    except Exception:
        pass


def run():
    # Allocate the drawing buffer before anything else; once memory fragments it silently comes back 0x0.
    C = L.newCanvas(W, PH, 16, 0)
    try:
        L.setFont(L.FONTS.DejaVu9)
        C.setFont(L.FONTS.DejaVu9)
    except Exception:
        pass
    L.fillScreen(BK)
    if not C.width():
        L.setTextColor(RD, BK)
        L.drawString("Clawd: no memory for the drawing buffer", 6, 60)
        return
    builtins.clawd_buf = (C.width(), C.height())
    L.setTextColor(OR, BK)
    L.drawString("Clawd is waking up...", 58, 58)
    L.setTextColor(GR, BK)
    L.drawString("checking the clock and weather", 40, 74)
    g = G()
    sync(g)
    # The speaker claims 8 KB on first use; do that before reserving. Tones under ~20 ms never
    # end on this build (a 1 ms tone buzzes forever), hence 20 ms plus an explicit stop.
    try:
        M5.Speaker.tone(18000, 20)
        time.sleep_ms(60)
        M5.Speaker.stop()
    except Exception:
        pass
    reserve(g, True)
    g.hol = holiday()
    read_battery(g)
    load(g)
    try:
        g.br = L.getBrightness()
    except Exception:
        pass
    L.fillScreen(BK)
    kb = MatrixKeyboard()
    time.sleep_ms(300)
    f = 0
    t_stats = t_save = time.ticks_ms()
    # Hardware watchdog: if the loop (or the firmware under it) freezes for a minute, the chip
    # restarts into Clawd. It can't be stopped once started; see the KeyboardInterrupt handler.
    wdt = machine.WDT(timeout=60000)
    try:
        while True:
            wdt.feed()
            t0 = time.ticks_ms()
            kb.tick()
            k = kb.get_key()
            if k:
                key(g, k)
            if g.buf and time.ticks_diff(t0, g.buf_t) > 8000:
                g.buf = ""
            m = tick(C, g, f)
            C.push(0, TOP)
            hud(g, m, f, f == 0)
            sound(g)
            if time.ticks_diff(t0, t_stats) >= 5000:
                stats(g, time.ticks_diff(t0, t_stats) / 60000, m)
                t_stats = t0
            if time.ticks_diff(t0, t_save) >= 300000:
                save(g)
                t_save = t0
            net_step(g)
            f += 1
            d = 75 - time.ticks_diff(time.ticks_ms(), t0)
            if d > 0:
                time.sleep_ms(d)
    except KeyboardInterrupt:
        # Ctrl-C over USB: hand both buffers back (a memory-starved REPL resets or freezes mid-upload)
        # and keep the watchdog fed so the REPL stays usable. The timer runs inside the
        # interpreter, so a frozen REPL still gets reset.
        reserve(g, False)
        C.delete()
        machine.Timer(3).init(period=10000, callback=lambda t: wdt.feed())
        raise
    except Exception as e:
        import sys
        sys.print_exception(e)
        L.fillScreen(BK)
        L.setTextColor(RD, BK)
        L.drawString("Clawd crashed, restarting:", 6, 52)
        L.drawString(str(e)[:38], 6, 68)
        save(g)
        time.sleep(5)
        machine.reset()
    finally:
        save(g)


# Setting builtins.clawd_test lets a REPL import this module without starting the loop.
# Only a bare name lookup sees it on this build; getattr(builtins, ...) does not.
try:
    clawd_test
except NameError:
    run()
