#!/usr/bin/env python3
"""Compile Clawd and install it on a Cardputer-Adv running UIFlow 2.5 (MicroPython 1.27).

    python3 tools/deploy.py            # compile, upload, reboot into Clawd
    python3 tools/deploy.py --clean    # also delete the conference bundle's leftover apps
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import device_serial as ds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEVICE = os.path.join(ROOT, "device")
BUILD = os.path.join(ROOT, "build")

# Files the Code with Claude conference bundle installs; --clean removes them.
LEFTOVERS = (
    "/flash/apps/claude_buddy.py", "/flash/apps/hello_cardputer.py", "/flash/apps/snake.py",
    "/flash/apps/clawd.py", "/flash/buddy_ble.py", "/flash/buddy_chars.py",
    "/flash/buddy_protocol.py", "/flash/buddy_state.py", "/flash/buddy_ui_cp.py",
    "/flash/burst_frames.py", "/flash/wifi_event.py",
)


def compile_core():
    version = subprocess.run([sys.executable, "-m", "mpy_cross", "--version"],
                             capture_output=True, text=True)
    if "mpy v6.3" not in version.stdout:
        sys.exit("Need mpy-cross for MicroPython 1.27 (mpy v6.3): pip install -r tools/requirements.txt\n"
                 "Got: " + (version.stdout or version.stderr).strip())
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "clawd_core.mpy")
    subprocess.run([sys.executable, "-m", "mpy_cross", "-o", out,
                    os.path.join(DEVICE, "clawd_core.py")], check=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port (default: first /dev/cu.usbmodem*)")
    ap.add_argument("--clean", action="store_true", help="delete the conference bundle's leftover files")
    ap.add_argument("--no-reboot", action="store_true", help="leave the device at the REPL")
    args = ap.parse_args()

    files = [
        (compile_core(), "/flash/clawd_core.mpy"),
        (os.path.join(DEVICE, "main.py"), "/flash/main.py"),
        (os.path.join(DEVICE, "clawd_wifi.py"), "/flash/clawd_wifi.py"),
    ]
    secrets = os.path.join(DEVICE, "clawd_secrets.py")
    if os.path.exists(secrets):
        files.append((secrets, "/flash/clawd_secrets.py"))
    else:
        print("No device/clawd_secrets.py: Clawd will run without WiFi (no clock sync, no weather).")

    s = ds.open_port(args.port)
    ds.interrupt(s)
    for local, remote in files:
        ds.upload(s, local, remote)

    # A .py next to the .mpy would win the import and fail to compile on the device.
    # boot_option=2 makes UIFlow's boot.py run /flash/main.py instead of its own launcher.
    setup = (
        "import os, esp32\n"
        "try:\n"
        "    os.remove('/flash/clawd_core.py')\n"
        "except OSError:\n"
        "    pass\n"
        "nvs = esp32.NVS('uiflow')\n"
        "nvs.set_u8('boot_option', 2)\n"
        "nvs.commit()\n"
        "print('BOOT_OPTION 2')\n"
    )
    if args.clean:
        setup += (
            "gone = []\n"
            "for p in %r:\n"
            "    try:\n"
            "        os.remove(p)\n"
            "        gone.append(p)\n"
            "    except OSError:\n"
            "        pass\n"
            "print('REMOVED', gone)\n" % (LEFTOVERS,)
        )
    print(ds.run(s, setup))
    if not args.no_reboot:
        ds.reset(s)
        print("Rebooting into Clawd.")
    s.close()


if __name__ == "__main__":
    main()
