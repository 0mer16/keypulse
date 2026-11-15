"""Lights a few keys by their OpenRGB names so you can check them against the physical keyboard.

    python -m tools.keycheck            (keeps the lights on for 5 minutes, Ctrl+C to stop)
"""
import time

from keypulse.openrgb.client import OpenRGB
from keypulse.openrgb.runtime import OpenRGBRuntime

CHECK = {
    "V": (255, 0, 0),            # red
    "B": (0, 60, 255),           # blue
    "/": (0, 255, 0),            # green
    "Right Shift": (255, 200, 0),  # yellow
    "Up Arrow": (255, 255, 255),   # white
    "Delete": (180, 0, 255),       # purple
}

rt = OpenRGBRuntime()
c = OpenRGB(port=rt.ensure(), name="KeyPulse key check")
kb = c.find("Everest")
names = {n[5:]: i for i, n in enumerate(kb.leds) if n.startswith("Key: ")}
c.direct_mode(kb)
colors = [(0, 0, 0)] * kb.led_count
for name, col in CHECK.items():
    colors[names[name]] = col
try:
    end = time.time() + 300
    while time.time() < end:
        c.set_colors(kb, colors)
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    c.close()
    rt.stop()

