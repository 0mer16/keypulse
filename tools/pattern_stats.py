"""Render every visualiser pattern over audio and report how bright and lively it is.

    python -m tools.pattern_stats [song.wav [seconds]]     (always includes the synthetic beat track)

  avg light   mean light the key LEDs emit (after LED contrast), 0..1
  peaks       98th percentile of frame brightness: how big the big moments get
  movement    mean change per frame: how much it dances
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

import tools.tuning_test as T
from keypulse.audio.features import Features
from keypulse.effects.base import KeyboardLayout, RenderContext
from keypulse.effects.visualizer import VisualizerEffect as V

fx = json.loads((Path(__file__).parent / "everest60_layout.json").read_text())
layout = KeyboardLayout(fx["matrix"], fx["led_count"], fx["leds"])
KEYS = [led for _, _, led in layout.key_cells]


def run(audio, rate, settings):
    eff = V(layout)
    s = V.defaults() | settings
    feat = Features(rate, 15)
    hop = rate // 60
    bright, move, prev = [], [], None
    for f in range(len(audio) // hop):
        fr = feat.update(audio[f * hop:(f + 1) * hop], 1 / 60)
        cols = np.array(eff.render(RenderContext(dt=1 / 60, now=f / 60, audio=fr), s))
        assert cols.shape == (layout.led_count, 3) and np.isfinite(cols).all() and cols.min() >= 0
        k = (np.clip(cols[KEYS], 0, 255) / 255) ** s["contrast"]
        bright.append(k.mean())
        if prev is not None:
            move.append(np.abs(k - prev).mean())
        prev = k
    b = np.array(bright[180:])
    return b.mean(), np.percentile(b, 98), np.mean(move[180:])


if __name__ == "__main__":
    sources = [("synthetic", T.synth()[0], T.RATE)]
    if len(sys.argv) > 1:
        with wave.open(sys.argv[1]) as w:
            rate = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else len(a) / rate
        sources.insert(0, ("song", a[: int(secs * rate)], rate))
    for name, audio, rate in sources:
        for pattern in ("bars", "mirror", "ripple", "flow"):
            m, p, mv = run(audio, rate, {"pattern": pattern})
            print(f"{name:9s} {pattern:6s} avg light {m:.2f}  peaks {p:.2f}  movement {mv:.3f}")
