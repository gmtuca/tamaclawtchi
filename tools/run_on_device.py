#!/usr/bin/env python3
"""Run a MicroPython script on the device and stream its output until a DONE line or the prompt.

    python3 tools/run_on_device.py tools/device_test.py --fresh --reset-after
    python3 tools/run_on_device.py --listen 300     # print Clawd's log lines for 5 minutes
--fresh reboots without starting Clawd, so the script gets fresh-boot memory; --reset-after reboots into Clawd.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import device_serial as ds  # noqa: E402


def reopen(port, wait):
    time.sleep(wait)
    for _ in range(60):
        try:
            return ds.open_port(port)
        except SystemExit:
            time.sleep(0.5)
    sys.exit("device did not come back after reboot")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?")
    ap.add_argument("--port")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--reset-after", action="store_true")
    ap.add_argument("--listen", type=float, metavar="SECONDS", help="only print the device's output")
    args = ap.parse_args()
    port = args.port or ds.find_port()

    s = ds.open_port(port)
    if args.listen:
        t0 = time.time()
        while time.time() - t0 < args.listen:
            line = s.readline().decode(errors="replace").rstrip()
            if line:
                print("%5.0fs %s" % (time.time() - t0, line), flush=True)
        return
    if not args.script:
        ap.error("give a script or --listen")

    if args.fresh:
        ds.interrupt(s)
        ds.run(s, "open('/flash/skip_clawd_once', 'w').close()")   # main.py skips Clawd for one boot
        ds.reset(s)
        s.close()
        s = reopen(port, 8)
    ds.interrupt(s)
    with open(args.script) as fh:
        ds.start(s, fh.read())

    t0 = time.time()
    tail = b""
    while time.time() - t0 < args.timeout:
        line = s.readline()
        if not line:
            continue
        tail = (tail + line)[-10:]
        text = line.decode(errors="replace").rstrip()
        if text and not text.startswith("=== "):
            print(text, flush=True)
        if text.startswith("DONE") or tail.endswith(ds.PROMPT):
            break
    else:
        print("TIMEOUT after %ss" % args.timeout)

    if args.reset_after:
        ds.interrupt(s)
        ds.reset(s)
        print("Rebooted into Clawd.")
    s.close()


if __name__ == "__main__":
    main()
