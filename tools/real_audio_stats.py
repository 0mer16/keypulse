"""How do the bars behave on real music? python -m tools.real_audio_stats file.wav [seconds]

  mean     average bar level (high = bars always full = feels unresponsive)
  full%    share of time bars sit above 80%
  dyn      average per-bar movement over time (std); higher = more dancing
  contrast mean level just after detected hits vs. the rest (higher = hits stand out)
  events   beats / accents / drops per minute
"""
import importlib
import sys
import wave

import numpy as np

FPS = 60


def stats(module, audio, rate):
    fx = importlib.import_module(module).Features(rate, 15)
    hop = rate // FPS
    L, hit, counts = [], [], {"beat": 0, "accent_hit": 0, "drop": 0}
    for f in range(len(audio) // hop):
        r = fx.update(audio[f * hop:(f + 1) * hop], 1 / FPS)
        L.append(r.levels.copy())
        h = False
        for k in counts:
            if getattr(r, k, 0):
                counts[k] += 1
                h = True
        hit.append(h)
    L = np.array(L)[FPS * 3:]               # skip warm-up
    hit = np.array(hit)[FPS * 3:]
    after = np.zeros(len(hit), bool)
    for i in np.where(hit)[0]:
        after[i:i + 6] = True
    m = L.mean(axis=1)
    mins = len(L) / FPS / 60
    return (f"mean {L.mean():.2f} | full% {(L > 0.8).mean() * 100:4.1f} | dyn {L.std(axis=0).mean():.3f} | "
            f"contrast {m[after].mean() - m[~after].mean():+.2f} | per min: "
            + ", ".join(f"{k} {v / mins:.0f}" for k, v in counts.items()))


if __name__ == "__main__":
    with wave.open(sys.argv[1]) as w:
        rate = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else len(a) / rate
    a = a[: int(secs * rate)]
    for mod in ("tools._baseline_features", "keypulse.audio.features"):   # baseline = an older copy, if present
        try:
            print(f"{mod:28s} {stats(mod, a, rate)}")
        except ModuleNotFoundError:
            pass

