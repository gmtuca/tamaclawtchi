"""Talk to the Cardputer's MicroPython REPL over USB serial (raw paste mode, no mpremote)."""

import base64
import glob
import sys
import time

import serial

PROMPT = b">>> "


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*")) + sorted(glob.glob("/dev/ttyACM*"))
    if not ports:
        sys.exit("No Cardputer found on USB. Plug it in with a data cable (not charge-only).")
    return ports[0]


def open_port(port=None):
    try:
        return serial.Serial(port or find_port(), 115200, timeout=0.2)
    except serial.SerialException as e:
        sys.exit("Could not open the port (%s). Close screen/picocom or anything else using it." % e)


def read_until(s, marker, timeout):
    buf = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = s.read(4096)
        if chunk:
            buf += chunk
            if marker in buf:
                return buf
    raise TimeoutError("device did not answer (waited %ss for %r); got: %r" % (timeout, marker, buf[-300:]))


def interrupt(s):
    """Stop whatever is running (Clawd exits to the REPL on Ctrl-C) and wait for a prompt."""
    for _ in range(5):
        s.write(b"\x03")
        time.sleep(0.05)
    s.write(b"\r\n")
    read_until(s, PROMPT, 5)
    time.sleep(0.2)
    s.read(65536)


def start(s, code):
    """Send code in paste mode and start it; the caller reads the output."""
    s.write(b"\x05")
    read_until(s, b"=== ", 3)
    for line in code.splitlines():
        s.write(line.encode() + b"\r")
        time.sleep(0.003)
    time.sleep(0.05)
    s.read(65536)   # discard the echo; nothing runs until Ctrl-D
    s.write(b"\x04")


def run(s, code, timeout=15):
    """Run code in paste mode and return its printed output."""
    start(s, code)
    out = read_until(s, PROMPT, timeout).decode(errors="replace")
    lines = [ln for ln in out.rsplit(">>> ", 1)[0].splitlines() if not ln.startswith("=== ")]
    return "\n".join(lines).strip()


def upload(s, local, remote, chunk=384):
    """Write a local file to the device, verifying the size afterwards."""
    with open(local, "rb") as fh:
        data = fh.read()
    run(s, "import ubinascii\n_f = open(%r, 'wb')" % remote)
    for i in range(0, len(data), chunk):
        run(s, "_f.write(ubinascii.a2b_base64(%r))" % base64.b64encode(data[i:i + chunk]).decode())
        sys.stderr.write("\r  %s: %d/%d bytes" % (remote, min(i + chunk, len(data)), len(data)))
    sys.stderr.write("\n")
    out = run(s, "_f.close()\nimport os\nprint('SIZE', os.stat(%r)[6])" % remote)
    if ("SIZE %d" % len(data)) not in out:
        raise RuntimeError("upload of %s did not verify: %s" % (remote, out))


def reset(s):
    """Reboot the device; it starts Clawd again via /flash/main.py."""
    s.write(b"import machine; machine.reset()\r\n")
    time.sleep(0.3)
