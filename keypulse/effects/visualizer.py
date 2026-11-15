"""Music visualiser: four patterns driven by body/hit levels, kicks, accents and drops.

Every pattern shares the same "moments":
  kick    -> a soft pulse (edge + a touch on the keys)
  accent  -> a flash scaled by how big the hit is compared with recent ones
  drop    -> a white shockwave across the whole keyboard
  hi-hat  -> sparkles
"""
import math
import random

import numpy as np

from .base import Control, Effect, KeyboardLayout, NO_LED, Preset, RenderContext, add, hex_to_rgb, hsv, mix, scale

PATTERNS = [("bars", "Bars"), ("mirror", "Mirror"), ("ripple", "Ripple"), ("flow", "Flow")]
COLOR_MODES = [("rainbow", "Rainbow"), ("single", "One colour"), ("two", "Two colours"), ("three", "Three colours")]
GRADIENTS = [("auto", "Automatic"), ("across", "Bass → treble"), ("up", "Bottom → top")]
EDGE_MODES = [("match", "Match the music"), ("cycle", "Colour cycle"), ("custom", "Custom colour"), ("off", "Off")]
LEGACY_MODES = {"two_h": ("two", "across"), "two_v": ("two", "up"), "three_v": ("three", "up")}

_mode = lambda *m: (lambda s: s.get("color_mode") in m)
_pattern = lambda *p: (lambda s: s.get("pattern") in p)


class VisualizerEffect(Effect):
    id = "visualizer"
    name = "Music Visualizer"
    description = "Lights that dance to whatever your PC is playing."
    uses_audio = True

    controls = [
        Control("pattern", "Pattern", "choice", "bars", "Pattern", options=PATTERNS),
        Control("color_mode", "Colours", "choice", "rainbow", "Colours", options=COLOR_MODES),
        Control("color1", "Colour 1", "color", "#00e5ff", "Colours", visible_if=_mode("single", "two", "three")),
        Control("color2", "Colour 2", "color", "#ff00c8", "Colours", visible_if=_mode("two", "three")),
        Control("color3", "Colour 3", "color", "#ffe600", "Colours", visible_if=_mode("three")),

        # ---- advanced ----
        Control("gradient", "Colour direction", "choice", "auto", "Colours", options=GRADIENTS,
                visible_if=_mode("two", "three", "rainbow"), advanced=True),
        Control("rainbow_shift", "Rainbow start", "slider", 0, "Colours", min=0, max=360, step=5, suffix="°",
                visible_if=_mode("rainbow"), advanced=True),
        Control("idle_glow", "Resting glow", "slider", 10, "Colours", min=0, max=40, suffix="%", advanced=True),
        Control("edge_mode", "Edge lights", "choice", "match", "Edge lights", options=EDGE_MODES, advanced=True),
        Control("edge_color", "Edge colour", "color", "#7a5cff", "Edge lights",
                visible_if=lambda s: s.get("edge_mode") == "custom", advanced=True),
        Control("beat_flash", "Flash on big hits", "toggle", True, "Beats & sparkle", advanced=True),
        Control("flash_color", "Flash colour", "color", "#ffffff", "Beats & sparkle",
                visible_if=lambda s: s.get("beat_flash"), advanced=True),
        Control("sparkles", "Hi-hat sparkles", "toggle", True, "Beats & sparkle", advanced=True),
        Control("sparkle_color", "Sparkle colour", "color", "#ffffff", "Beats & sparkle",
                visible_if=lambda s: s.get("sparkles"), advanced=True),
        Control("peak_dots", "Peak dots", "toggle", True, "Beats & sparkle",
                visible_if=_pattern("bars", "mirror"), advanced=True),
        Control("sensitivity", "Sensitivity", "slider", 100, "Tuning", min=40, max=300, step=10, suffix="%",
                advanced=True),
        Control("fall_speed", "Fall speed", "slider", 6, "Tuning", min=1, max=10, advanced=True),
        Control("contrast", "LED contrast", "slider", 1.9, "Tuning", min=1.0, max=2.6, step=0.1, advanced=True,
                help="Higher = deeper darks and punchier peaks"),
    ]

    presets = [
        Preset("Rainbow", {"color_mode": "rainbow", "edge_mode": "match"}),
        Preset("Fire", {"color_mode": "three", "gradient": "up", "color1": "#ff1a00", "color2": "#ff7a00",
                        "color3": "#ffe14d", "edge_mode": "custom", "edge_color": "#ff3300",
                        "flash_color": "#ffd28a"}),
        Preset("Ocean", {"color_mode": "two", "color1": "#0040ff", "color2": "#00ffd5", "flash_color": "#bff6ff"}),
        Preset("Neon", {"color_mode": "two", "color1": "#ff00c8", "color2": "#00e5ff", "edge_mode": "cycle"}),
        Preset("Matrix", {"color_mode": "single", "color1": "#00ff41", "edge_mode": "custom",
                          "edge_color": "#00a82b", "flash_color": "#b6ffb6", "sparkle_color": "#d4ffd4"}),
        Preset("VU meter", {"color_mode": "three", "gradient": "up", "color1": "#00ff3c", "color2": "#ffd000",
                            "color3": "#ff0000"}),
        Preset("Sunset", {"color_mode": "three", "gradient": "up", "color1": "#ff4500", "color2": "#ff2e88",
                          "color3": "#7b2cff", "edge_mode": "custom", "edge_color": "#ff5e3a",
                          "flash_color": "#ffd1a8", "sparkle_color": "#ffe0b3"}),
        Preset("Vaporwave", {"color_mode": "two", "color1": "#ff71ce", "color2": "#01cdfe", "edge_mode": "custom",
                             "edge_color": "#b967ff", "flash_color": "#fffb96", "sparkle_color": "#05ffa1"}),
        Preset("Ice", {"color_mode": "two", "gradient": "up", "color1": "#0a3cff", "color2": "#e6f7ff",
                       "edge_mode": "custom", "edge_color": "#5ad1ff"}),
        Preset("Galaxy", {"color_mode": "three", "gradient": "up", "color1": "#1a0b5e", "color2": "#7b2cff",
                          "color3": "#ff4fd8", "edge_mode": "cycle"}),
        Preset("Cyberpunk", {"color_mode": "two", "color1": "#fcee0a", "color2": "#00f0ff", "edge_mode": "custom",
                             "edge_color": "#ff003c", "flash_color": "#ff003c", "sparkle_color": "#00f0ff"}),
        Preset("Toxic", {"color_mode": "two", "gradient": "up", "color1": "#00ff2a", "color2": "#c8ff00",
                         "edge_mode": "custom", "edge_color": "#8a00ff", "flash_color": "#c8ff00",
                         "sparkle_color": "#8a00ff"}),
        Preset("Party", {"color_mode": "rainbow", "idle_glow": 0, "edge_mode": "cycle"}),
        Preset("Minimal", {"color_mode": "single", "color1": "#ffffff", "idle_glow": 0, "edge_mode": "off",
                           "beat_flash": False, "sparkles": False}),
    ]
    PRESET_SECTIONS = ("Colours", "Edge lights", "Beats & sparkle")

    PEAK_HOLD = 0.3
    PEAK_GRAVITY = 16.0
    SPARKLE_LIFE = 0.16
    RING_SPEED = 13.0          # cells per second
    RING_LIFE = 1.2

    @classmethod
    def migrate(cls, values):
        """Settings saved by v0.1 used combined colour modes."""
        legacy = LEGACY_MODES.get(values.get("color_mode"))
        if legacy:
            values["color_mode"], values["gradient"] = legacy

    def __init__(self, layout: KeyboardLayout):
        super().__init__(layout)
        self.n, self.rows = len(layout.KEY_COLS), len(layout.KEY_ROWS)
        self.height = np.zeros(self.n)
        self.vel = np.zeros(self.n)
        self.peak = np.zeros(self.n)
        self.peak_age = np.zeros(self.n)
        self.peak_vel = np.zeros(self.n)
        self.flow = np.zeros((self.rows, self.n))      # [row (0 = bottom)][col], newest on the right
        self.flow_acc = 0.0
        self.rings = []                                # [age, strength, palette t, whiteness]
        self.sparkles = {}
        self.pulse = self.flash = self.burst = 0.0
        self.cycle_hue = 0.0
        self.ring_t = 0.0
        self.upper_keys = [cell for cell in layout.key_cells if cell[0] in layout.KEY_ROWS[:2]]
        self.cx, self.cy = (self.n - 1) / 2, (self.rows - 1) / 2

    def output_gamma(self, s):
        return float(s.get("contrast", 1.9))

    # ---------- colours ----------
    def _palette_fn(self, s):
        mode = s["color_mode"]
        legacy = LEGACY_MODES.get(mode)
        if legacy:
            mode = legacy[0]
        c1, c2, c3 = (hex_to_rgb(s[k]) for k in ("color1", "color2", "color3"))
        shift = s["rainbow_shift"] / 360.0
        if mode == "rainbow":
            return lambda t: hsv(shift + 0.8 * t, 1, 1)
        if mode == "single":
            return lambda t: c1
        if mode == "two":
            return lambda t: mix(c1, c2, t)
        return lambda t: mix(c1, c2, t * 2) if t < 0.5 else mix(c2, c3, (t - 0.5) * 2)

    def _direction(self, s):
        g = s.get("gradient", "auto")
        mode = LEGACY_MODES.get(s["color_mode"], (s["color_mode"], None))
        if mode[1]:
            return mode[1]
        if g == "auto":
            return "up" if mode[0] == "three" else "across"
        return g

    # ---------- main ----------
    def render(self, ctx: RenderContext, s: dict) -> list:
        L = self.layout
        dt, r = ctx.dt, ctx.audio
        n, rows = self.n, self.rows
        levels = r.levels if r is not None else np.zeros(n)
        hits = r.hits if r is not None and r.hits is not None else np.zeros(n)
        loud = r.loudness if r is not None else 0.0
        bass = r.bass if r is not None else 0.0
        pal = self._palette_fn(s)
        across = self._direction(s) == "across"

        # ---- moments ----
        pattern = s.get("pattern", "bars")
        ripple = pattern == "ripple"
        if r is not None:
            if r.beat:
                self.pulse = max(self.pulse, r.beat)
                self.cycle_hue += 0.05
                if ripple:
                    self._ring(r.beat * 0.8, 0.0)
            if r.accent_hit:
                self.flash = max(self.flash, r.accent_hit)
                if ripple:
                    self._ring(0.6 + 0.4 * r.accent_hit, 0.25 if r.accent_hit >= 0.8 else 0.0)
                elif r.accent_hit >= 0.9 and s["beat_flash"]:
                    self._ring(0.45, 0.6)              # the biggest hits send a faint shockwave
            if r.drop:
                self.burst = max(self.burst, r.drop)
                self.flash = 1.0
                self._ring(1.0, 0.8, wide=True)
                self.cycle_hue += 0.2
            if r.hat and s["sparkles"] and self.upper_keys:
                for _ in range(1 + int(r.hat * 2)):
                    self.sparkles[random.choice(self.upper_keys)[2]] = 0.0
        self.pulse *= math.exp(-dt * 8)
        self.flash *= math.exp(-dt * 7)
        self.burst *= math.exp(-dt * 4)
        self.cycle_hue += dt * 0.03
        self.ring_t += dt * 0.05
        for ring in self.rings:
            ring[0] += dt
        self.rings = [ring for ring in self.rings if ring[0] < self.RING_LIFE]

        # ---- per-pattern key brightness: grid[row k][col i] = (value 0..1, palette t, white tint) ----
        if pattern == "flow":
            grid = self._flow(levels, hits, dt, s)
        elif pattern == "ripple":
            grid = self._ripple(levels, bass)
        elif pattern == "mirror":
            grid = self._bars(levels, hits, dt, s, mirror=True)
        else:
            grid = self._bars(levels, hits, dt, s)

        colors = [(0.0, 0.0, 0.0)] * L.led_count
        idle = s["idle_glow"] / 100.0 * (0.5 + 0.5 * loud)
        flash_rgb = hex_to_rgb(s["flash_color"])
        if s["edge_mode"] == "cycle":
            accent_rgb = hsv(self.cycle_hue, 1, 1)
        elif s["edge_mode"] == "custom":
            accent_rgb = hex_to_rgb(s["edge_color"])
        else:
            w = levels + 1e-3
            accent_rgb = pal(float(np.dot(np.linspace(0, 1, n), w) / w.sum()))
        big = max(0.0, self.flash - 0.55) / 0.45 if s["beat_flash"] else 0.0   # only big hits light the keys

        for k in range(rows):
            for i, c in enumerate(L.KEY_COLS):
                led = L.at(L.KEY_ROWS[rows - 1 - k], c)
                if led == NO_LED:
                    continue
                v, t, white = grid[k][i]
                if t is None:
                    t = i / (n - 1) if across else k / (rows - 1)
                base = pal(t)
                col = scale(base, idle + (1 - idle) * v) if v > 0 else scale(base, idle)
                if white > 0:
                    col = mix(col, (255, 255, 255), min(1.0, white))
                col = add(col, scale(accent_rgb, 0.10 * self.pulse))
                ring = self._ring_value(i, k)
                if ring[0] > 0:
                    col = add(col, scale(mix(pal(ring[1]), (255, 255, 255), ring[2]), ring[0]))
                if big > 0:
                    col = add(col, scale(flash_rgb, 0.22 * big))
                if self.burst > 0.02:
                    col = mix(col, flash_rgb, 0.75 * self.burst)
                colors[led] = col

        sparkle_rgb = hex_to_rgb(s["sparkle_color"])
        for led, age in list(self.sparkles.items()):
            if age > self.SPARKLE_LIFE:
                del self.sparkles[led]
                continue
            colors[led] = mix(colors[led], sparkle_rgb, 1 - age / self.SPARKLE_LIFE)
            self.sparkles[led] = age + dt

        if s["edge_mode"] != "off":
            glow = 0.07 + 0.5 * bass + 0.3 * self.pulse
            edge = scale(accent_rgb, min(1.0, glow))
            if s["beat_flash"]:
                edge = mix(edge, flash_rgb, min(1.0, self.flash * 0.9))
            if self.burst > 0.02:
                edge = mix(edge, flash_rgb, self.burst)
            for led in L.edge_ring:
                colors[led] = edge
        return colors

    # ---------- patterns ----------
    def _gravity(self, levels, dt, s, max_h):
        target = levels * max_h
        up = target > self.height
        self.height = np.where(up, target, self.height)
        self.vel = np.where(up, 0.0, self.vel + 8.0 * s["fall_speed"] * dt)
        self.height = np.where(up, self.height, np.maximum(target, self.height - self.vel * dt))
        hit = self.height >= self.peak
        self.peak = np.where(hit, self.height, self.peak)
        self.peak_age = np.where(hit, 0.0, self.peak_age + dt)
        self.peak_vel = np.where(hit | (self.peak_age < self.PEAK_HOLD), 0.0, self.peak_vel + self.PEAK_GRAVITY * dt)
        self.peak = np.maximum(self.height, self.peak - self.peak_vel * dt)

    def _bars(self, levels, hits, dt, s, mirror=False):
        n, rows = self.n, self.rows
        if mirror:
            # centre column = bass, outer columns = treble
            idx = [min(n - 1, int(round(abs(i - self.cx) * 2))) for i in range(n)]
            lv, ht = levels[idx], hits[idx]
            self._gravity(lv, dt, s, rows / 2 + 0.5)
        else:
            lv, ht = levels, hits
            self._gravity(lv, dt, s, rows)
        grid = [[(0.0, None, 0.0)] * n for _ in range(rows)]
        for i in range(n):
            h, pk = self.height[i], self.peak[i]
            tcol = abs(i - self.cx) / self.cx if mirror else None
            for k in range(rows):
                dk = abs(k - self.cy) if mirror else k      # distance from where the bar grows
                fill = min(1.0, max(0.0, h - dk))
                white = 0.45 * ht[i] if fill > 0 and h - dk < 1.2 else 0.0   # glint on the tip when hit
                if s["peak_dots"] and int(pk) == int(dk) and pk - h > 0.35 and pk > 0.5:
                    fill, white = max(fill, 0.8), 0.5
                grid[k][i] = (fill, tcol, white)
        return grid

    def _ripple(self, levels, bass):
        n, rows = self.n, self.rows
        grid = []
        for k in range(rows):
            row = []
            for i in range(n):
                # a field that follows the spectrum; the rings do the talking
                v = 0.5 * levels[i] + 0.3 * bass
                t = abs(i - self.cx) / self.cx
                row.append((v, t, 0.0))
            grid.append(row)
        return grid

    def _flow(self, levels, hits, dt, s):
        n, rows = self.n, self.rows
        per_row = len(levels) // rows
        newest = np.array([max(levels[j * per_row:(j + 1) * per_row].max(),
                               hits[j * per_row:(j + 1) * per_row].max()) for j in range(rows)])
        self.flow_acc += dt * 1.6 * (s["fall_speed"] + 2)        # ~13 columns/s at the default speed
        while self.flow_acc >= 1.0:
            self.flow = np.roll(self.flow, -1, axis=1)
            self.flow[:, -1] = 0.0
            self.flow_acc -= 1.0
        self.flow[:, -1] = np.maximum(self.flow[:, -1], newest)
        grid = []
        for k in range(rows):
            row = []
            for i in range(n):
                age = (n - 1 - i) / (n - 1)
                v = min(1.0, self.flow[k, i] * 1.25) ** 0.8 * (1 - 0.3 * age)
                row.append((v, k / (rows - 1), 0.0))
            grid.append(row)
        return grid

    # ---------- rings ----------
    def _ring(self, strength, whiteness, wide=False):
        self.rings.append([0.0, min(1.0, strength * 1.3), self.ring_t % 1.0, whiteness, 2.0 if wide else 1.4])
        self.ring_t += 0.17
        if len(self.rings) > 8:
            self.rings.pop(0)

    def _ring_value(self, i, k):
        best = (0.0, 0.0, 0.0)
        for age, strength, t, white, width in self.rings:
            radius = age * self.RING_SPEED
            d = math.hypot((i - self.cx) * 0.9, (k - self.cy) * 1.6)
            v = strength * math.exp(-((d - radius) / width) ** 2) * (1 - age / self.RING_LIFE) ** 1.5
            if v > best[0]:
                best = (v, t, white)
        return best
