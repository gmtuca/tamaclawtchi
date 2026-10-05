# On-device test for Clawd (runs ON the Cardputer): python3 tools/run_on_device.py tools/device_test.py --fresh --reset-after
# Exercises every scene, event, side activity, weather kind, holiday and key through the real code,
# in the same start-up order as run(). --fresh boots without Clawd so memory matches a real boot.
# It can't see the screen; use tools/render_screenshots.py for visuals.
import builtins
import gc
import time

builtins.clawd_test = True   # import clawd_core without starting its main loop
import clawd_core as c

fails = 0


def check(name, ok, info=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name, info)
    if not ok:
        fails += 1


# Same order as run(): drawing buffer, then WiFi, then speaker set-up and the memory reserve.
C = c.L.newCanvas(c.W, c.PH, 16, 0)
check("full-size drawing buffer at boot", (C.width(), C.height()) == (c.W, c.PH), (C.width(), C.height()))
try:
    C.setFont(c.L.FONTS.DejaVu9)
except Exception:
    pass
g = c.G()
g.mute = True   # stays quiet all run, e.g. in an office (only the inaudible 18 kHz warm-up below)
c.sync(g)
check("weather fetched at boot", g.temp is not None, (g.temp, g.hum, g.wk))
check("clock set", c.clock_ok(), time.localtime())
check("wifi off after sync", not c.network.WLAN(c.network.STA_IF).active())
c.M5.Speaker.tone(18000, 20)
time.sleep_ms(60)
c.M5.Speaker.stop()
c.reserve(g, True)
import esp32
info = esp32.idf_heap_info(esp32.HEAP_DATA)
print("INFO before reserve: free", sum(b[1] for b in info), "largest", max(b[2] for b in info))
for _ in range(7):   # stats() retries every 5 s while network buffers drain
    if g.res is not None:
        break
    time.sleep(5)
    c.reserve(g, True)
print("INFO memory reserve:", g.res and (g.res.width(), g.res.height()),
      "(often None here: compiling this test uses memory; tools/boot_check.py checks a real boot)")
f = 0


def frames(n):
    global f
    for i in range(n):
        m = c.tick(C, g, f)
        C.push(0, c.TOP)
        c.hud(g, m, f, i == 0)
        c.sound(g)
        f += 1


def at(hh, mm):
    g.sim = ((hh * 60 + mm) * 60 - c.live_secs()) % 86400


SCHEDULE = ((5, 0, "sleeping"), (8, 0, "coffee"), (8, 45, "commute"), (9, 45, "coffee"),
            (10, 30, "working"), (12, 0, "lunch"), (14, 0, "coffee"), (16, 0, "working"),
            (17, 45, "commute"), (18, 40, "workout"), (19, 30, "lunch"), (21, 0, "tv time"),
            (22, 0, "playtime"), (22, 45, "reading"), (23, 30, "sleeping"))
for hh, mm, want in SCHEDULE:
    at(hh, mm)
    frames(3)
    for e in c.EVENTS[g.scene]:
        c.start_ev(g, e)
        frames(8)
    check("schedule %02d:%02d" % (hh, mm), c.LABEL[g.scene] == want, c.LABEL[g.scene])
    if g.scene == c.WORK:
        check("tests pass is rare, not a normal work event", "ship" not in c.EVENTS[c.WORK], c.EVENTS[c.WORK])
        c.start_ev(g, "ship")
        frames(8)
        check("tests pass still plays", g.ev == "ship", g.ev)

at(12, 0)
for s in c.SIDES:
    c.set_side(g, s)
    frames(160 if s == c.VOLLEY else 40)
    check("side activity " + c.LABEL[s], g.scene == s)
    if s == c.DANCE:
        check("dancing runs the dance routine", g.sub == 0, g.sub)
    if s == c.CART:
        check("cartwheels run the acrobatics routine", g.sub == 1, g.sub)
print("INFO volleyball score", g.score)

c.set_side(g, None)
frames(2)
seen = []
for _ in range(len(c.CYCLE)):
    c.key(g, ord("/"))
    frames(2)
    seen.append(c.LABEL[g.scene])
check("right arrow cycles all side activities and back", seen[-1] == "lunch", seen)
c.key(g, 183)
frames(2)
check("Fn+right arrow", g.scene == c.SIDES[0], c.LABEL[g.scene])
c.key(g, 180)
frames(2)
check("Fn+left arrow back to schedule", g.side is None)

for wk in range(7):
    g.wk = wk
    for s in (None, c.BIKE, c.VOLLEY):
        c.set_side(g, s)
        frames(5)
    at(1, 0)
    frames(5)
    at(12, 0)
    check("weather kind %d draws indoors and outdoors" % wk, True)
c.set_side(g, None)

for hol in ("xmas", "newyear", "valentine", "easter", "halloween", "bonfire"):
    g.hol = hol
    for hh in (10, 21, 1):
        at(hh, 30)
        frames(25)
    check("holiday " + hol, True)
g.hol = None
check("easter 2027 is 28 March", c.easter(2027) == (3, 28), c.easter(2027))

at(2, 0)
frames(3)
g.f = 50
c.key(g, ord("a"))
frames(20)
check("feeding at night eats the fish", g.bub == "yum", g.bub)
g.f = 99
c.key(g, ord("a"))
frames(18)
check("feeding when full refuses", g.bub == "full", g.bub)
c.key(g, 0x09)
check("tab unmutes", not g.mute)
c.key(g, 0x09)
check("tab mutes", g.mute)
c.key(g, ord("?"))
check("? opens the key list", g.help > 0)
frames(3)
c.key(g, ord("x"))
check("any key closes the key list without feeding", g.help == 0 and g.fq == 0)
for k in (ord("1"), ord("4"), ord("3"), ord("0"), 0x0D):
    c.key(g, k)
check("typing 1430 + enter jumps to 14:30", c.minutes(g) == 870, c.minutes(g))
c.key(g, 0x0D)
check("enter alone returns to live time", g.sim is None)

g.f, g.need = 20, 0
at(12, 0)
frames(2)
c.stats(g, 0.1, 720)
check("hunger shows the fish bubble", g.bub == "fish", g.bub)

c.read_battery(g)
check("battery level reads 0-100", g.bat is not None and 0 <= g.bat <= 100, g.bat)
for g.bat in (9, 60):
    for i in range(10):
        c.hud(g, 720, i, i == 0)
check("battery icon draws when low and normal", True)

gc.collect()
print("INFO free memory", gc.mem_free())
print("RESULT", fails, "failure(s)")
print("DONE")
