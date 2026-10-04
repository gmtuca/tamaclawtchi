# WiFi helpers for Clawd. The network name and password live in clawd_secrets.py, which is not in git.
import time

import network
from clawd_secrets import PASSWORD, SSID


def connect(timeout_ms=7000):
    """Blocking connect, then set the clock from NTP. Returns True if connected."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        sta.connect(SSID, PASSWORD)
        t0 = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            time.sleep_ms(200)
    sync_clock()
    return True


def begin():
    """Start connecting without waiting; poll network.WLAN(network.STA_IF).isconnected()."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.connect(SSID, PASSWORD)


def sync_clock():
    """Set the RTC to UTC from NTP. Returns True on success."""
    try:
        import ntptime
        ntptime.settime()
        return True
    except Exception as e:
        print("clawd: clock sync failed:", e)
        return False
