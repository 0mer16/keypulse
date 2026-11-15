"""Offline tuning bench (run from the repo root: python -m tools.tuning_test): synthesise a beat track and score an analyser on it.

    python tuning_test.py

Scores, for the old and new analysers:
  beats   - kicks caught (within 60 ms) and false beats
  motion  - average bar movement per frame (higher = livelier)
  spread  - how different the 15 bars are from each other (higher = more shape)
  breakdown - average bar level in a quiet breakdown (should be clearly lower than with the beat)
"""
import numpy as np

RATE = 48000
BPM = 124
FPS = 60


BREAK = (6.0, 10.0)   # beat for 0-6 s, quiet breakdown 6-10 s, beat again 10-16 s


def synth(seconds=16, seed=1):
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    beat = 60 / BPM
    in_break = (t >= BREAK[0]) & (t < BREAK[1])
    # pad chord through the whole track (quieter in the breakdown)
    pad = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6, 440)) * 0.03
    out += pad * np.where(in_break, 0.5, 1.0)
    kicks, hats = [], []
    k = 0.25
    i = 0
    while k < seconds - 0.2:
        if BREAK[0] <= k < BREAK[1]:
            k += beat
            i += 1
            continue
        s = int(k * RATE)
        # kick: pitch drop 150 -> 45 Hz with fast decay
        L = int(0.25 * RATE)
        tt = np.arange(L) / RATE
        f = 45 + 105 * np.exp(-tt * 30)
        kick = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-tt * 9) * 0.8
        out[s:s + L] += kick[:n - s]
        kicks.append(k)
        # snare on beats 2 and 4
        if i % 2 == 1:
            Ls = int(0.18 * RATE)
            sn = rng.standard_normal(Ls) * np.exp(-np.arange(Ls) / RATE * 22) * 0.25
            out[s:s + Ls] += sn[:n - s]
        # bassline note per beat
        note = [55, 55, 65.4, 49][i % 4]
        Lb = int(beat * RATE * 0.9)
        tb = np.arange(Lb) / RATE
        bass = np.sign(np.sin(2 * np.pi * note * tb)) * 0.12 * np.exp(-tb * 3)
        out[s:s + Lb] += bass[:n - s]
        # hats on 8ths
        for off in (0, beat / 2):
            hs = int((k + off) * RATE)
            Lh = int(0.04 * RATE)
            hat = np.diff(rng.standard_normal(Lh + 1)) * np.exp(-np.arange(Lh) / RATE * 90) * 0.12
            out[hs:hs + Lh] += hat[:n - hs]
            hats.append(k + off)
        k += beat
        i += 1
    return out.astype(np.float32), np.array(kicks)


def score(name, step):
    """step(chunk, dt) -> (levels array, beat bool)."""
    audio, kicks = synth()
    hop = RATE // FPS
    levels, beats = [], []
    for f in range(len(audio) // hop):
        lv, beat = step(audio[f * hop:(f + 1) * hop], 1 / FPS)
        levels.append(np.asarray(lv, float))
        if beat:
            beats.append((f + 1) * hop / RATE)
    L = np.array(levels)
    beats = np.array(beats)
    hit = sum(np.any(np.abs(beats - k) < 0.06) for k in kicks) if len(beats) else 0
    false = sum(not np.any(np.abs(kicks - b) < 0.06) for b in beats)
    b0, b1 = int(BREAK[0] * FPS), int(BREAK[1] * FPS)
    loud = np.r_[L[FPS:b0], L[b1:]]
    motion = np.abs(np.diff(loud, axis=0)).mean()
    spread = loud.std(axis=1).mean()
    break_lv = L[b0 + FPS:b1].mean()      # skip the first second of the breakdown
    print(f"{name:9s} beats {hit:2d}/{len(kicks)} caught, {false:2d} false | motion {motion:.3f} | "
          f"spread {spread:.3f} | breakdown {break_lv:.2f} vs beat {loud.mean():.2f}")




def new_step_factory():
    from keypulse.audio.features import Features
    fx = Features(RATE, 15)

    def step(chunk, dt):
        r = fx.update(chunk, dt)
        return r.levels, r.beat > 0
    return step


if __name__ == "__main__":
    score("keypulse", new_step_factory())
