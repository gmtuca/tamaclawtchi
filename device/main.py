# Boots straight into Clawd, before anything else can fragment the memory its drawing buffer needs.
import os

import M5

M5.begin()
try:
    os.remove("/flash/skip_clawd_once")   # tools/run_on_device.py --fresh: boot to an idle REPL once
except OSError:
    import clawd_core
