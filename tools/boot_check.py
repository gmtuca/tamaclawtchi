# Checks a real boot (runs ON the Cardputer): python3 tools/run_on_device.py tools/boot_check.py --reset-after
# Run without --fresh, at least ~30 s after Clawd started, so it reads what his own start-up got.
# Ctrl-C stops Clawd but these builtins values survive. The on-device test can't check this itself:
# compiling the test script uses memory a real boot never does.
import esp32
import gc

info = esp32.idf_heap_info(esp32.HEAP_DATA)
gc.collect()
print("drawing buffer (want 240 x 97):", clawd_buf)
print("memory reserve bytes (want > 0):", clawd_res)
print("system memory free", sum(b[1] for b in info), "largest block", max(b[2] for b in info))
print("MicroPython heap free", gc.mem_free())
print("DONE")
