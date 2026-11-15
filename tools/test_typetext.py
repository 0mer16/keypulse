"""Offline checks for Type to Light: python -m tools.test_typetext"""
import json
from pathlib import Path

from keypulse.effects.base import KeyboardLayout, RenderContext
from keypulse.effects.keymap import key_name
from keypulse.effects.typetext import TypeTextEffect as T

fx = json.loads((Path(__file__).parent / "everest60_layout.json").read_text())
layout = KeyboardLayout(fx["matrix"], fx["led_count"], fx["leds"])
name_of = {i: n[5:] for i, n in enumerate(fx["leds"]) if n.startswith("Key: ")}

# 1. every printable ASCII character either maps to a real key or is deliberately unmapped
unmapped = [ch for ch in map(chr, range(33, 127)) if layout.key_leds.get(key_name(ch)) is None]
print("unmapped printable characters:", unmapped or "none")


def run(settings, seconds, fps=60):
    eff = T(layout)
    s = T.defaults() | settings
    frames = []
    for _ in range(int(seconds * fps)):
        cols = eff.render(RenderContext(dt=1 / fps, now=0.0), s)
        lit = {name_of[i]: max(c) / 255 for i, c in enumerate(cols) if i in name_of and max(c) > 40}
        frames.append(lit)
    return frames


# 2. spell HELLO: order of the brightest key per frame, and the blink between the two Ls
frames = run({"text": "HELLO", "style": "spell", "speed": 2, "pause": 0.5, "trail": 0, "bg_level": 0}, 3.0)
order = []
for f in frames:
    top = max(f, key=f.get) if f else "-"
    if not order or order[-1] != top:
        order.append(top)
print("spell order:", " ".join(order))
l_frames = [f.get("L", 0) for f in frames[60:120]]          # the two L slots: 1.0 s .. 2.0 s
dip = min(l_frames[20:40])
print(f"L brightness between the two Ls dips to {dip:.2f} (should be ~0 for a visible blink)")

# 3. typewriter: letters accumulate
frames = run({"text": "HI!", "style": "typewriter", "speed": 4, "pause": 0.6, "bg_level": 0}, 1.0)
print("typewriter lit keys at 0.2s / 0.45s / 0.7s:", sorted(frames[12]), sorted(frames[27]), sorted(frames[42]))

# 4. neon: whole word at once; space is a pause
frames = run({"text": "GO GO", "style": "neon", "bg_level": 0}, 0.5)
print("neon lit keys:", sorted(frames[-1]))

# 5. shifted symbols reuse their key
print("'?' ->", key_name("?"), "| '@' ->", key_name("@"), "| 'a' ->", key_name("a"), "| ' ' ->", key_name(" "))

# 6. physically verified correction: typing V must light the LED OpenRGB labels "B", and vice versa
from keypulse.effects.keymap import led_for
assert led_for("v", layout.key_leds) == layout.key_leds["B"]
assert led_for("B", layout.key_leds) == layout.key_leds["V"]
assert led_for("N", layout.key_leds) == layout.key_leds["N"]
print("V/B correction: OK")


# 7. "On key press": each press lights the next letter
def run_keys(settings, presses, seconds, fps=60):
    """presses: times (s) at which a key goes down. Returns lit keys sampled just after each press, and at the end."""
    eff = T(layout)
    s = T.defaults() | settings
    assert eff.wants_keys(s)
    frames, pending = [], sorted(presses)
    for f in range(int(seconds * fps)):
        t = f / fps
        keys = []
        while pending and pending[0] <= t:
            pending.pop(0)
            keys.append(0x41)
        cols = eff.render(RenderContext(dt=1 / fps, now=t, keys=keys), s)
        frames.append({name_of[i]: max(c) / 255 for i, c in enumerate(cols) if i in name_of and max(c) > 40})
    return frames


fps = 60
presses = [0.5, 1.0, 1.5, 2.0, 2.5, 3.5]       # HELLO, then one more press after the word is done
fr = run_keys({"text": "HELLO", "style": "keypress", "hold": True, "glow": 0.5, "bg_level": 0,
               "complete_flash": False, "idle_reset": 0}, presses, 4.0)
for p in presses:
    print(f"  after press at {p:.1f}s: {sorted(fr[int(p * fps) + 6])}")
fr = run_keys({"text": "HELLO", "style": "keypress", "hold": True, "bg_level": 0, "idle_reset": 1.0},
              [0.2, 0.4], 2.5)
print("idle reset: lit at 0.5s", sorted(fr[30]), "| lit at 2.0s", sorted(fr[120]) or "nothing (reset)")
fr = run_keys({"text": "HI", "style": "keypress", "hold": False, "glow": 0.5, "bg_level": 0,
               "complete_flash": False, "idle_reset": 0}, [0.1], 1.0)
print("fade mode: H at 0.15s", round(fr[9].get("H", 0), 2), "| at 0.7s", fr[42].get("H", "faded out"))
fr = run_keys({"text": "HI", "style": "keypress", "hint": True, "bg_level": 0, "idle_reset": 0}, [0.1], 0.5)
print("hint: before any press, dim keys", sorted(fr[3]), "| after pressing, hint moves to", sorted(fr[20]))
