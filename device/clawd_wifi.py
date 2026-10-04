# WiFi helpers for Clawd. Known networks live in clawd_secrets.py, which is not in git.
import time

import clawd_secrets
import network

NETWORKS = getattr(clawd_secrets, "NETWORKS", None) or [(clawd_secrets.SSID, clawd_secrets.PASSWORD)]
_pick = 0   # index into NETWORKS of the network to try next


def current():
    return NETWORKS[_pick][0]


def next_network():
    global _pick
    _pick = (_pick + 1) % len(NETWORKS)


def _choose_strongest(sta):
    global _pick
    try:
        seen = {s[0].decode(): s[3] for s in sta.scan()}   # ssid -> signal strength (RSSI)
    except Exception as e:
        print("clawd: wifi scan failed:", e)
        return
    known = [i for i, (ssid, _) in enumerate(NETWORKS) if ssid in seen]
    if known:
        _pick = max(known, key=lambda i: seen[NETWORKS[i][0]])


def connect(timeout_ms=7000):
    """Blocking: join the strongest known network in range, then set the clock. Returns True if connected."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        _choose_strongest(sta)
        for _ in NETWORKS:
            ssid, password = NETWORKS[_pick]
            sta.connect(ssid, password)
            t0 = time.ticks_ms()
            while not sta.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
                time.sleep_ms(200)
            if sta.isconnected():
                break
            sta.disconnect()
            next_network()
        else:
            return False
    print("clawd: wifi connected to", current())
    sync_clock()
    return True


def begin():
    """Start joining the current network without waiting; poll network.WLAN(network.STA_IF).isconnected()."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    ssid, password = NETWORKS[_pick]
    sta.connect(ssid, password)


def sync_clock():
    """Set the RTC to UTC from NTP. Returns True on success."""
    try:
        import ntptime
        ntptime.settime()
        return True
    except Exception as e:
        print("clawd: clock sync failed:", e)
        return False
