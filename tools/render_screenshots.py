#!/usr/bin/env python3
"""Render Clawd scenes to PNG by running device/clawd_core.py against a fake M5 graphics API.

    python3 tools/render_screenshots.py              # all shots into docs/screenshots/
    python3 tools/render_screenshots.py work coffee  # only these
Shapes and layout match the device; fonts, colours and brightness are close but not identical."""

import builtins
import calendar
import os
import random
import sys
import time
import types

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "screenshots")
SCALE = 3
FONTS = {1: ImageFont.load_default(10), 2: ImageFont.load_default(18)}


def rgb(c):
    # The panel is RGB565, so quantise the same way.
    r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    return (r & 0xF8 | r >> 5, g & 0xFC | g >> 6, b & 0xF8 | b >> 5)


class Surface:
    """The subset of the M5GFX drawing API that clawd_core uses."""

    def __init__(self, w, h):
        self.img = Image.new("RGB", (w, h))
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"
        self.fg, self.size = 0xFFFFFF, 1

    def width(self):
        return self.img.width

    def height(self):
        return self.img.height

    def fillScreen(self, c):
        self.fillRect(0, 0, self.img.width, self.img.height, c)

    def fillRect(self, x, y, w, h, c):
        if w > 0 and h > 0:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb(c))

    def fillCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(c))

    def drawCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], outline=rgb(c))

    def drawRect(self, x, y, w, h, c):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], outline=rgb(c))

    def fillEllipse(self, x, y, rx, ry, c):
        self.d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=rgb(c))

    def fillTriangle(self, x0, y0, x1, y1, x2, y2, c):
        self.d.polygon([(x0, y0), (x1, y1), (x2, y2)], fill=rgb(c))

    def fillRoundRect(self, x, y, w, h, r, c):
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], r, fill=rgb(c))

    def drawRoundRect(self, x, y, w, h, r, c):
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], r, outline=rgb(c))

    def drawLine(self, x0, y0, x1, y1, c):
        self.d.line([(x0, y0), (x1, y1)], fill=rgb(c))

    def setTextColor(self, fg, bg=None):
        self.fg = fg

    def setTextSize(self, s):
        self.size = s

    def setFont(self, f):
        pass

    def textWidth(self, s):
        return int(self.d.textlength(s, font=FONTS[self.size]))

    def drawString(self, s, x, y):
        self.d.text((x, y - 1), s, fill=rgb(self.fg), font=FONTS[self.size])

    def push(self, x, y):
        LCD.img.paste(self.img, (x, y))

    def delete(self):
        pass


class Lcd(Surface):
    FONTS = types.SimpleNamespace(DejaVu9=None)

    def newCanvas(self, w, h, bpp, psram):
        return Surface(w, h)

    def setBrightness(self, v):
        pass

    def getBrightness(self):
        return 100


LCD = Lcd(240, 135)


def load_clawd():
    m5 = types.ModuleType("M5")
    m5.Lcd = LCD
    m5.Speaker = types.SimpleNamespace(tone=lambda *a: None, stop=lambda: None)
    m5.Power = types.SimpleNamespace(getBatteryLevel=lambda: 78, isCharging=lambda: False)
    m5.begin = lambda: None
    machine = types.ModuleType("machine")
    machine.reset = lambda: None
    network = types.ModuleType("network")
    network.STA_IF = 0
    network.WLAN = lambda *a: types.SimpleNamespace(active=lambda *a: False, isconnected=lambda: False)
    hardware = types.ModuleType("hardware")
    hardware.MatrixKeyboard = object
    sys.modules.update({"M5": m5, "machine": machine, "network": network, "hardware": hardware})
    time.ticks_ms = lambda: int(time.monotonic() * 1000)
    time.ticks_diff = lambda a, b: a - b
    time.ticks_add = lambda a, b: a + b
    time.sleep_ms = lambda ms: None
    # MicroPython has no time zones: localtime() is UTC and mktime() takes an 8-tuple in UTC.
    time.localtime = time.gmtime
    time.mktime = lambda t: calendar.timegm(tuple(t[:6]) + (0, 0, 0))
    builtins.clawd_test = True
    sys.path.insert(0, os.path.join(ROOT, "device"))
    import clawd_core
    return clawd_core


c = load_clawd()


def shot(name, hh, mm, frames, wk=None, temp=16.4, hum=72, hol=None, side=None, at=None, bat=78, chg=False):
    """Run the real code for `frames` frames at hh:mm and save the last frame. `at(g, f)` runs before each frame."""
    random.seed(7)
    g = c.G()
    g.temp, g.hum, g.hol, g.bat, g.chg = temp, hum, hol, bat, chg
    g.wk = c.PARTLY if wk is None else wk
    c.live_secs = lambda: (hh * 60 + mm) * 60   # a live clock, so the header has no time-travel "~"
    if side is not None:
        c.set_side(g, side)
    canvas = LCD.newCanvas(c.W, c.PH, 16, 0)
    for f in range(frames):
        if at:
            at(g, f)
        m = c.tick(canvas, g, f)
        canvas.push(0, c.TOP)
        c.hud(g, m, f, f == 0)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    LCD.img.resize((c.W * SCALE, c.H * SCALE), Image.NEAREST).save(path)
    print("wrote", os.path.relpath(path, ROOT))


def feed(g, f):
    if f == 0:
        c.key(g, ord("a"))


def keys(g, f):
    if f == 2:
        c.key(g, ord("?"))


SHOTS = {
    "work": lambda: shot("work", 10, 30, 47),
    "coffee": lambda: shot("coffee", 8, 5, 14, wk=c.CLEAR, temp=11.2, hum=81),
    "commute": lambda: shot("commute", 8, 50, 21, wk=c.RAIN, temp=12.8, hum=93),
    "lunch": lambda: shot("lunch", 12, 15, 147, wk=c.CLEAR, temp=19.5, hum=58),
    "feed": lambda: shot("feed", 15, 40, 8, at=feed),
    "volleyball": lambda: shot("volleyball", 13, 30, 23, wk=c.CLEAR, temp=24.1, hum=49, side=c.VOLLEY),
    "bike": lambda: shot("bike", 11, 0, 30, wk=c.CLEAR, temp=21.0, hum=55, side=c.BIKE),
    "music": lambda: shot("music", 16, 20, 33, wk=c.OVERCAST, temp=14.0, hum=77, side=c.MUSIC),
    "dance": lambda: shot("dance", 22, 0, 56, wk=c.CLEAR, side=c.DANCE),
    "tv": lambda: shot("tv", 21, 0, 41),
    "sleep-xmas": lambda: shot("sleep-xmas", 2, 0, 60, wk=c.SNOW, temp=-1.5, hum=88, hol="xmas"),
    "read-halloween": lambda: shot("read-halloween", 22, 40, 24, wk=c.FOG, temp=9.3, hum=96, hol="halloween"),
    "keys": lambda: shot("keys", 10, 30, 6, at=keys),
}


if __name__ == "__main__":
    for name in sys.argv[1:] or SHOTS:
        SHOTS[name]()
