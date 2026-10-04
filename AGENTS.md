# Notes for coding agents

Read `README.md` first, especially **Learnings and gotchas**: most "obvious" changes on this device fail silently.

- The whole app is `device/clawd_core.py`. Deploy with `python3 tools/deploy.py`, then verify with
  `python3 tools/run_on_device.py tools/device_test.py --fresh --reset-after` (expect `RESULT 0 failure(s)`).
  Add a check to `tools/device_test.py` for anything new.
- You cannot see the screen. The test proves the code runs, not that it looks right: ask the user to look.
- Never commit `device/clawd_secrets.py` (WiFi credentials; git-ignored).
- Memory is the constraint (about 60 KB of MicroPython heap, no PSRAM). Keep the drawing buffer allocated
  first at boot, keep WiFi off between checks, keep the 24 KB reserve, keep notes 40 ms or longer.
- Before deploying, check for duplicate top-level names (the README has a one-liner); a clash already broke a scene.
