"""How quickly does the analyser react? python -m tools.latency_test

Plays synthetic hits after silence/steady music and measures, for each hit:
  rise  - ms until the affected bars reach half of their peak
  beat  - ms until a beat/accent event fires (if any)
"""
import importlib

import numpy as np

RATE, FPS = 48000, 60


def kick(n=0.25):
    t = np.arange(int(n * RATE)) / RATE
    f = 45 + 105 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 9) * 0.8


def snare(n=0.18, seed=3):
    t = np.arange(int(n * RATE)) / RATE
    return np.random.default_rng(seed).standard_normal(len(t)) * np.exp(-t * 22) * 0.35


def sub808(n=0.6, f=41.2):
    t = np.arange(int(n * RATE)) / RATE
    return np.sin(2 * np.pi * f * t) * np.minimum(1, t / 0.005) * np.exp(-t * 2) * 0.7


def scene():
    """Steady background music bed, with hits at known times."""
    secs = 8
    t = np.arange(secs * RATE) / RATE
    rng = np.random.default_rng(0)
    bed = sum(np.sin(2 * np.pi * f * t) for f in (220, 330, 440)) * 0.02 + rng.standard_normal(len(t)) * 0.003
    hits = [("kick", 2.0, kick(), slice(0, 3)), ("808", 4.0, sub808(), slice(0, 3)),
            ("snare", 6.0, snare(), slice(6, 12))]
    out = bed.copy()
    for _, at, sig, _ in hits:
        s = int(at * RATE)
        out[s:s + len(sig)] += sig
    return out.astype(np.float32), hits


def measure(module):
    Features = importlib.import_module(module).Features
    audio, hits = scene()
    fx = Features(RATE, 15)
    hop = RATE // FPS
    rows = []
    for f in range(len(audio) // hop):
        r = fx.update(audio[f * hop:(f + 1) * hop], 1 / FPS)
        rows.append((((f + 1) * hop) / RATE, r))
    res = []
    for name, at, _, bands in hits:
        win = [(t, r) for t, r in rows if at - 0.1 <= t <= at + 0.4]
        base = np.mean([r.levels[bands].mean() for t, r in win if t < at])
        peak = max(r.levels[bands].mean() for t, r in win)
        half = base + (peak - base) / 2
        rise = next((t - at for t, r in win if t >= at and r.levels[bands].mean() >= half), None)
        ev = [t - at for t, r in win if t >= at - 0.02 and (r.beat or getattr(r, "accent_hit", 0))]
        res.append(f"{name:5s} rise {rise * 1000:4.0f} ms (bars {base:.2f}->{peak:.2f})  "
                   f"event {'%.0f ms' % (ev[0] * 1000) if ev else 'none'}")
    return res


if __name__ == "__main__":
    for mod in ("tools._baseline_features", "keypulse.audio.features"):
        try:
            print(f"--- {mod}")
            for line in measure(mod):
                print("   ", line)
        except ModuleNotFoundError:
            pass
