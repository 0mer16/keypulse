"""Turns live audio into lighting-friendly features.

    fx = Features(rate, bands=15)
    r = fx.update(samples, dt)   # call once per frame with the new audio and frame time
    r.levels    -> 0..1 per band, each band scaled to its own recent range, with onset punch
    r.beat      -> >0 on the frame a kick/bass hit starts (strength 0..1)
    r.hat       -> >0 on the frame a hi-hat / snare / transient starts (strength 0..1)
    r.loudness  -> 0..1 overall loudness relative to the last ~10 s (quiet intro vs drop)

All time constants are in seconds, so behaviour doesn't change with frame rate.
"""
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class Frame:
    levels: np.ndarray
    beat: float
    hat: float
    loudness: float


def _band_bins(freqs, lo, hi, centre):
    idx = np.where((freqs >= lo) & (freqs < hi))[0]
    return idx if len(idx) else np.array([np.argmin(np.abs(freqs - centre))])


def _decay(per_second, dt):
    """Amount to move this frame for a rate given per second."""
    return per_second * dt


class Onset:
    """Detects sudden rises in a dB signal with an adaptive threshold."""

    def __init__(self, min_rise_db, min_gap_s, sensitivity=1.5, history_s=2.0, lookback=3):
        self.min_rise, self.min_gap, self.k = min_rise_db, min_gap_s, sensitivity
        self.history_s, self.lookback = history_s, lookback
        self.recent = deque(maxlen=lookback)
        self.flux_hist = deque()
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
            return float(min(1.0, rise / (threshold * 2.5)) * 0.5 + 0.5)
        return 0.0


class Features:
    def __init__(self, rate, bands=15, fmin=35.0, fmax=16000.0, gain=1.0,
                 range_db=18.0, punch=0.45, gamma=1.3, shape=0.5):
        self.rate, self.gain = rate, gain
        self.range_db, self.punch, self.gamma = range_db, punch, gamma
        self.long_n, self.short_n = 4096, 1024
        self.buf = np.zeros(self.long_n, np.float32)
        self.win_long = np.hanning(self.long_n).astype(np.float32)
        self.win_short = np.hanning(self.short_n).astype(np.float32)
        f_long = np.fft.rfftfreq(self.long_n, 1 / rate)
        f_short = np.fft.rfftfreq(self.short_n, 1 / rate)

        edges = np.geomspace(fmin, fmax, bands + 1)
        centres = np.sqrt(edges[:-1] * edges[1:])
        # bass bands need fine frequency resolution (long FFT); highs need speed (short FFT)
        self.bands = []
        for lo, hi, c in zip(edges[:-1], edges[1:], centres):
            if c < 250:
                self.bands.append(("long", _band_bins(f_long, lo, hi, c)))
            else:
                self.bands.append(("short", _band_bins(f_short, lo, hi, c)))
        self.n_bands = bands
        self.tilt = 3.0 * np.log2(centres / 1000)   # +3 dB/octave so treble isn't drowned by bass
        self.shape_ref = -40.0
        self.shape = shape
        self.kick_bins = _band_bins(f_short, 40, 160, 80)      # fast kick detector
        self.hat_bins = _band_bins(f_short, 5000, 14000, 8000)  # hats / snare crack

        self.ceil = np.full(bands, -60.0)
        self.floor = np.full(bands, -80.0)
        self.prev_db = np.full(bands, -80.0)
        self.loud_ceil = -40.0
        self.kick = Onset(min_rise_db=5.0, min_gap_s=0.22, sensitivity=1.4)
        self.hats = Onset(min_rise_db=4.0, min_gap_s=0.07, sensitivity=1.4)

    def _push(self, samples):
        n = len(samples)
        if n >= self.long_n:
            self.buf[:] = samples[-self.long_n:]
        elif n:
            self.buf = np.roll(self.buf, -n)
            self.buf[-n:] = samples

    def update(self, samples, dt):
        self._push(np.asarray(samples, np.float32) * self.gain)
        spec_long = np.abs(np.fft.rfft(self.buf * self.win_long)) ** 2 / self.long_n
        short = self.buf[-self.short_n:]
        spec_short = np.abs(np.fft.rfft(short * self.win_short)) ** 2 / self.short_n * 4

        power = np.array([(spec_long if which == "long" else spec_short)[idx].mean()
                          for which, idx in self.bands])
        db = 10 * np.log10(power + 1e-12)

        # overall loudness vs the last ~10 s, and a silence gate
        rms_db = 20 * np.log10(np.sqrt(np.mean(short ** 2)) + 1e-9)
        self.loud_ceil = max(rms_db, self.loud_ceil - _decay(0.6, dt))
        loudness = float(np.clip((rms_db - (self.loud_ceil - 24)) / 24, 0, 1))
        if rms_db < -65:
            loudness = 0.0

        # each band keeps its own range: ceiling jumps up instantly and relaxes slowly,
        # floor creeps up slowly and drops quickly, with a minimum span
        self.ceil = np.maximum(db, self.ceil - _decay(4.0, dt))
        self.floor = np.where(db < self.floor, self.floor + (db - self.floor) * 0.3,
                              self.floor + _decay(2.5, dt))
        self.floor = np.minimum(self.floor, self.ceil - self.range_db)
        own = np.clip((db - self.floor) / (self.ceil - self.floor), 0, 1)

        # shared reference keeps the spectrum's shape (bass vs mids vs treble)
        tilted = db + self.tilt
        self.shape_ref = max(tilted.max(), self.shape_ref - _decay(3.0, dt))
        shared = np.clip((tilted - (self.shape_ref - 30)) / 30, 0, 1)
        norm = ((1 - self.shape) * own + self.shape * shared) ** self.gamma

        # onset punch: a band that just jumped gets an extra kick
        rise = np.clip((db - self.prev_db) / 8.0, 0, 1)
        self.prev_db = db
        levels = np.clip(norm + self.punch * rise, 0, 1)
        levels *= 0.35 + 0.65 * loudness        # quiet passages stay calmer

        kick_db = 10 * np.log10(spec_short[self.kick_bins].sum() + 1e-12)
        hat_db = 10 * np.log10(spec_short[self.hat_bins].sum() + 1e-12)
        beat = self.kick.update(kick_db, dt) if loudness > 0.05 else 0.0
        hat = self.hats.update(hat_db, dt) if loudness > 0.05 else 0.0
        return Frame(levels, beat, hat, loudness)
