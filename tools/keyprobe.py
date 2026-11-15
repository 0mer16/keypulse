"""Light one or more keys by OpenRGB name: python -m tools.keyprobe "/=00ff00" "Up Arrow=ffffff" """
import sys, time
from keypulse.openrgb.client import OpenRGB
from keypulse.openrgb.runtime import OpenRGBRuntime

rt = OpenRGBRuntime()
c = OpenRGB(port=rt.ensure(), name="KeyPulse key probe")
kb = c.find("Everest")
names = {n[5:] if n.startswith("Key: ") else n: i for i, n in enumerate(kb.leds)}
colors = [(0, 0, 0)] * kb.led_count
for arg in sys.argv[1:]:
    name, hexcol = arg.rsplit("=", 1)
    colors[names[name]] = tuple(int(hexcol[i:i + 2], 16) for i in (0, 2, 4))
c.direct_mode(kb)
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
