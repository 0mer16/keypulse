"""Turns live audio into lighting-friendly features.

    fx = Features(rate, bands=15)
    r = fx.update(samples, dt)   # call once per frame with the new audio and frame time

    r.levels      0..1 per band: a calm "body" from sustained sound plus a sharp jump when that band is hit
    r.body        0..1 per band: just the sustained part
    r.hits        0..1 per band: just the transient part (decays quickly)
    r.beat        >0 on the frame a kick starts; strength is relative to recent kicks (big kick = big value)
    r.accent      0..1 continuous: how hard the whole spectrum is being hit right now
    r.accent_hit  >0 on the frame of a stand-out hit anywhere (snare, clap, 808, impact); strength 0..1
    r.drop        >0 on the frame the music slams back in after a quieter stretch
    r.hat         >0 on the frame a hi-hat / cymbal starts
    r.bass        0..1 fast bass envelope
    r.loudness    0..1 overall loudness relative to the last ~10 s

All time constants are in seconds, so behaviour doesn't change with frame rate.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Frame:
    levels: np.ndarray
    beat: float
    hat: float
    loudness: float
    body: np.ndarray = None
    hits: np.ndarray = None
    accent: float = 0.0
    accent_hit: float = 0.0
    drop: float = 0.0
    bass: float = 0.0


def _band_bins(freqs, lo, hi, centre):
    idx = np.where((freqs >= lo) & (freqs < hi))[0]
    return idx if len(idx) else np.array([np.argmin(np.abs(freqs - centre))])


class RunningStats:
    """Exponentially-weighted mean/std over roughly `seconds`."""

    def __init__(self, seconds, init_mean=0.0, init_var=1.0):
        self.seconds, self.mean, self.var = seconds, init_mean, init_var

    def update(self, x, dt):
        a = min(1.0, dt / self.seconds)
        d = x - self.mean
        self.mean += a * d
        self.var = (1 - a) * (self.var + a * d * d)
        return self.mean, np.sqrt(np.maximum(self.var, 1e-9))


class Onset:
    """Sudden rise in a dB signal, judged against its own recent history.

    Returns 0, or on the frame of an onset a strength in 0.3..1 that compares this hit with recent
    ones: an ordinary hit is ~0.5, an unusually big one approaches 1."""

    def __init__(self, min_rise_db, min_gap_s, sensitivity=1.4, history_s=2.0, lookback=3):
        self.min_rise, self.min_gap, self.k = min_rise_db, min_gap_s, sensitivity
        self.history_s = history_s
        self.recent = deque(maxlen=lookback)
        self.flux_hist = deque()
        self.hit_sizes = deque(maxlen=16)
        self.since = 1e9

    def update(self, db, dt):
        self.since += dt
        db = max(db, -70.0)       # digital silence must not look like a 100+ dB jump afterwards
        rise = db - min(self.recent) if self.recent else 0.0
        self.recent.append(db)
        self.flux_hist.append(min(max(rise, 0.0), 24.0))
        while len(self.flux_hist) > max(8, self.history_s / max(dt, 1e-3)):
            self.flux_hist.popleft()
        h = np.fromiter(self.flux_hist, float)
        threshold = max(self.min_rise, h.mean() + self.k * h.std())
        if rise > threshold and self.since >= self.min_gap:
            self.since = 0.0
            typical = np.median(self.hit_sizes) if self.hit_sizes else rise
            self.hit_sizes.append(rise)
            rel = rise / max(typical, 1e-3)              # 1.0 = a typical hit
            return float(np.clip(0.5 + 0.5 * (rel - 1) / 0.6, 0.3, 1.0))
        return 0.0


class Features:
    def __init__(self, rate, bands=15, fmin=35.0, fmax=16000.0, gain=1.0, range_db=18.0,
                 body_gamma=1.5, body_max=0.7, hit_weight=1.0, accent_z=3.3, drop_db=10.0):
        self.rate, self.gain, self.range_db = rate, gain, range_db
        self.body_gamma, self.body_max, self.hit_weight = body_gamma, body_max, hit_weight
        self.accent_z, self.drop_db = accent_z, drop_db
        self.long_n, self.short_n = 2048, 1024      # 2048 (43 ms) for bass detail, 1024 (21 ms) for speed
        self.buf = np.zeros(self.long_n, np.float32)
        self.win_long = np.hanning(self.long_n).astype(np.float32)
        self.win_short = np.hanning(self.short_n).astype(np.float32)
        f_long = np.fft.rfftfreq(self.long_n, 1 / rate)
        f_short = np.fft.rfftfreq(self.short_n, 1 / rate)

        edges = np.geomspace(fmin, fmax, bands + 1)
        centres = np.sqrt(edges[:-1] * edges[1:])
        self.bands = []
        for lo, hi, c in zip(edges[:-1], edges[1:], centres):
            which, freqs = ("long", f_long) if c < 250 else ("short", f_short)
            self.bands.append((which, _band_bins(freqs, lo, hi, c)))
        self.n_bands = bands
        self.tilt = 3.0 * np.log2(centres / 1000)   # +3 dB/octave so treble isn't drowned by bass
        # how much each band counts towards "accent" hits: bass and snare region matter most
        self.accent_w = np.interp(np.log2(centres), np.log2([40, 120, 250, 2500, 8000, 16000]),
                                  [1.4, 1.4, 1.0, 1.1, 0.6, 0.3])
        self.kick_bins = _band_bins(f_short, 30, 160, 70)
        self.hat_bins = _band_bins(f_short, 6000, 15000, 9000)

        self.ceil = np.full(bands, -60.0)
        self.floor = np.full(bands, -80.0)
        self.shape_ref = -40.0
        self.recent_db = deque(maxlen=3)
        self.flux_stats = [RunningStats(1.5, 0.5, 4.0) for _ in range(bands)]
        self.hits = np.zeros(bands)
        self.accent_stats = RunningStats(3.0, 2.0, 9.0)
        self.accent_since = 1e9
        self.accent_sizes = deque(maxlen=16)
        self.loud_ceil = -40.0
        self.loud_fast = -80.0
        self.loud_slow = deque()
        self.drop_since = 1e9
        self.bass_env = 0.0
        self.bass_ceil = -50.0
        self.kick = Onset(min_rise_db=5.0, min_gap_s=0.2, sensitivity=1.4)
        self.hats = Onset(min_rise_db=5.0, min_gap_s=0.09, sensitivity=1.8)

    def _push(self, samples):
        n = len(samples)
        if n >= self.long_n:
            self.buf[:] = samples[-self.long_n:]
        elif n:
            self.buf = np.roll(self.buf, -n)
            self.buf[-n:] = samples

    def update(self, samples, dt):
        self._push(np.asarray(samples, np.float32) * self.gain)
        spec_long = np.abs(np.fft.rfft(self.buf * self.win_long)) ** 2 / self.long_n * 2
        short = self.buf[-self.short_n:]
        spec_short = np.abs(np.fft.rfft(short * self.win_short)) ** 2 / self.short_n * 4
        power = np.array([(spec_long if which == "long" else spec_short)[idx].mean() for which, idx in self.bands])
        db = np.maximum(10 * np.log10(power + 1e-12), -90.0)

        # ---- loudness, silence gate, drops ----
        rms_db = 20 * np.log10(np.sqrt(np.mean(short ** 2)) + 1e-9)
        self.loud_ceil = max(rms_db, self.loud_ceil - 0.6 * dt)
        loudness = float(np.clip((rms_db - (self.loud_ceil - 24)) / 24, 0, 1))
        silent = rms_db < -65
        if silent:
            loudness = 0.0
        # instant attack, ~0.25 s release: a kick-heavy re-entry registers as loud on its first hit
        level_now = max(rms_db, -80.0)
        if level_now > self.loud_fast:
            self.loud_fast = level_now
        else:
            self.loud_fast += min(1.0, dt / 0.25) * (level_now - self.loud_fast)
        self.loud_slow.append(self.loud_fast)
        while len(self.loud_slow) > max(10, 3.0 / max(dt, 1e-3)):
            self.loud_slow.popleft()
        self.drop_since += dt
        drop = 0.0
        # a drop = the last ~3 s were *mostly* quiet (median, so short gaps between phrases don't count)
        # and the music has just slammed back in near full volume
        if len(self.loud_slow) > 30 and not silent and self.drop_since > 8:
            hist = np.fromiter(self.loud_slow, float)
            quiet_before = float(np.median(hist[: int(len(hist) * 0.8)]))
            if self.loud_fast - quiet_before > self.drop_db and self.loud_fast > self.loud_ceil - 9:
                drop = float(np.clip((self.loud_fast - quiet_before - self.drop_db) / 10 + 0.6, 0.6, 1.0))
                self.drop_since = 0.0

        # ---- body: each band in its own recent range, blended with the overall spectrum shape ----
        self.ceil = np.maximum(db, self.ceil - 4.0 * dt)
        self.floor = np.where(db < self.floor, self.floor + (db - self.floor) * 0.3, self.floor + 2.5 * dt)
        self.floor = np.minimum(self.floor, self.ceil - self.range_db)
        own = np.clip((db - self.floor) / (self.ceil - self.floor), 0, 1)
        tilted = db + self.tilt
        self.shape_ref = max(tilted.max(), self.shape_ref - 3.0 * dt)
        shared = np.clip((tilted - (self.shape_ref - 30)) / 30, 0, 1)
        body = (0.5 * own + 0.5 * shared) ** self.body_gamma * self.body_max   # sustained sound fills ~70%

        # ---- hits: per-band rise vs that band's own typical rise ----
        rise = np.maximum(db - np.min(np.array(self.recent_db), axis=0), 0) if self.recent_db else np.zeros_like(db)
        self.recent_db.append(db)
        z = np.zeros(self.n_bands)
        for b in range(self.n_bands):
            mu, sd = self.flux_stats[b].update(min(rise[b], 24.0), dt)
            z[b] = (rise[b] - mu) / (sd + 0.5)
        new_hits = np.clip((z - 1.0) / 2.5, 0, 1) * (rise > 3.0)
        self.hits = np.maximum(new_hits, self.hits * np.exp(-dt / 0.09))    # sharp, ~90 ms decay

        loud_scale = 0.3 + 0.7 * loudness
        levels = np.clip(body + self.hit_weight * self.hits, 0, 1) * loud_scale

        # ---- accents: the whole spectrum jumping at once ----
        flux = float(np.sum(np.minimum(rise, 18.0) * self.accent_w))
        mu, sd = self.accent_stats.update(flux, dt)
        az = (flux - mu) / (sd + 1.0)
        accent = float(np.clip((az - 0.5) / 3.0, 0, 1)) * (not silent)
        self.accent_since += dt
        accent_hit = 0.0
        if az > self.accent_z and flux > 25 and self.accent_since > 0.16 and not silent:
            # rank this hit against the last 16: the biggest recent hit flashes hardest
            prev = np.fromiter(self.accent_sizes, float)
            rank = float(np.mean(prev < flux)) if len(prev) else 0.5
            self.accent_sizes.append(flux)
            accent_hit = 0.3 + 0.7 * rank ** 3
            self.accent_since = 0.0

        # ---- bass envelope (fast attack, quick release) for glows ----
        kick_db = 10 * np.log10(spec_short[self.kick_bins].sum() + 1e-12)
        self.bass_ceil = max(kick_db, self.bass_ceil - 2.0 * dt)
        target = float(np.clip((kick_db - (self.bass_ceil - 20)) / 20, 0, 1)) ** 1.5 * loud_scale
        self.bass_env = target if target > self.bass_env else self.bass_env + (target - self.bass_env) * min(1, dt / 0.12)

        hat_db = 10 * np.log10(spec_short[self.hat_bins].sum() + 1e-12)
        beat = self.kick.update(kick_db, dt) if loudness > 0.05 else 0.0
        hat = self.hats.update(hat_db, dt) if loudness > 0.05 else 0.0
        return Frame(levels=levels, beat=beat, hat=hat, loudness=loudness, body=body * loud_scale,
                     hits=self.hits * loud_scale, accent=accent, accent_hit=accent_hit, drop=drop,
                     bass=float(self.bass_env))
