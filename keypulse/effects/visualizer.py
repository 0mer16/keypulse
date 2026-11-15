"""Music visualiser: spectrum bars on the keys, a reactive edge ring, beat punches and hi-hat sparkles."""
import math
import random

import numpy as np

from .base import (Control, Effect, KeyboardLayout, NO_LED, Preset, RenderContext,
                   add, hex_to_rgb, hsv, mix, scale)

COLOR_MODES = [
    ("rainbow", "Rainbow"),
    ("single", "One colour"),
    ("two_h", "Two colours: bass → treble"),
    ("two_v", "Two colours: bottom → top"),
    ("three_v", "Three colours: bottom → top"),
]
EDGE_MODES = [("match", "Match the bars"), ("cycle", "Colour cycle"), ("custom", "Custom colour"), ("off", "Off")]

_uses = lambda *modes: (lambda s: s.get("color_mode") in modes)


class VisualizerEffect(Effect):
    id = "visualizer"
    name = "Music Visualizer"
    description = "Spectrum bars that dance to whatever your PC is playing."
    uses_audio = True

    controls = [
        Control("color_mode", "Colour style", "choice", "rainbow", "Colours", options=COLOR_MODES),
        Control("rainbow_shift", "Rainbow start", "slider", 0, "Colours", min=0, max=360, step=5, suffix="°",
                visible_if=_uses("rainbow")),
        Control("color1", "Colour 1", "color", "#00e5ff", "Colours",
                visible_if=_uses("single", "two_h", "two_v", "three_v")),
        Control("color2", "Colour 2", "color", "#ff00c8", "Colours", visible_if=_uses("two_h", "two_v", "three_v")),
        Control("color3", "Colour 3", "color", "#ffe600", "Colours", visible_if=_uses("three_v")),
        Control("idle_glow", "Unlit key glow", "slider", 6, "Colours", min=0, max=40, suffix="%"),

        Control("edge_mode", "Edge lights", "choice", "match", "Edge lights", options=EDGE_MODES),
        Control("edge_color", "Edge colour", "color", "#7a5cff", "Edge lights",
                visible_if=lambda s: s.get("edge_mode") == "custom"),

        Control("beat_flash", "Flash edge on beats", "toggle", True, "Beats & sparkle"),
        Control("flash_color", "Flash colour", "color", "#ffffff", "Beats & sparkle",
                visible_if=lambda s: s.get("beat_flash")),
        Control("beat_punch", "Pulse keys on beats", "toggle", True, "Beats & sparkle"),
        Control("sparkles", "Hi-hat sparkles", "toggle", True, "Beats & sparkle"),
        Control("sparkle_color", "Sparkle colour", "color", "#ffffff", "Beats & sparkle",
                visible_if=lambda s: s.get("sparkles")),
        Control("peak_dots", "Peak dots", "toggle", True, "Beats & sparkle"),

        Control("sensitivity", "Sensitivity", "slider", 100, "Tuning", min=40, max=300, step=10, suffix="%"),
        Control("fall_speed", "Bar fall speed", "slider", 5, "Tuning", min=1, max=10),
    ]

    presets = [
        Preset("Rainbow", {"color_mode": "rainbow", "rainbow_shift": 0, "edge_mode": "match", "flash_color": "#ffffff"}),
        Preset("Fire", {"color_mode": "three_v", "color1": "#ff1a00", "color2": "#ff7a00", "color3": "#ffe14d",
                        "edge_mode": "custom", "edge_color": "#ff3300", "flash_color": "#ffd28a"}),
        Preset("Ocean", {"color_mode": "two_h", "color1": "#0040ff", "color2": "#00ffd5",
                         "edge_mode": "match", "flash_color": "#bff6ff"}),
        Preset("Neon", {"color_mode": "two_h", "color1": "#ff00c8", "color2": "#00e5ff",
                        "edge_mode": "cycle", "flash_color": "#ffffff"}),
        Preset("Matrix", {"color_mode": "single", "color1": "#00ff41", "edge_mode": "custom",
                          "edge_color": "#00a82b", "flash_color": "#b6ffb6", "sparkle_color": "#d4ffd4"}),
        Preset("VU meter", {"color_mode": "three_v", "color1": "#00ff3c", "color2": "#ffd000", "color3": "#ff0000",
                            "edge_mode": "match", "flash_color": "#ffffff"}),
        Preset("Sunset", {"color_mode": "three_v", "color1": "#ff4500", "color2": "#ff2e88", "color3": "#7b2cff",
                          "edge_mode": "custom", "edge_color": "#ff5e3a", "flash_color": "#ffd1a8",
                          "sparkle_color": "#ffe0b3"}),
        Preset("Vaporwave", {"color_mode": "two_h", "color1": "#ff71ce", "color2": "#01cdfe", "edge_mode": "custom",
                             "edge_color": "#b967ff", "flash_color": "#fffb96", "sparkle_color": "#05ffa1"}),
        Preset("Ice", {"color_mode": "two_v", "color1": "#0a3cff", "color2": "#e6f7ff", "idle_glow": 10,
                       "edge_mode": "custom", "edge_color": "#5ad1ff", "flash_color": "#ffffff"}),
        Preset("Galaxy", {"color_mode": "three_v", "color1": "#1a0b5e", "color2": "#7b2cff", "color3": "#ff4fd8",
                          "idle_glow": 10, "edge_mode": "cycle", "flash_color": "#ffffff"}),
        Preset("Cyberpunk", {"color_mode": "two_h", "color1": "#fcee0a", "color2": "#00f0ff", "edge_mode": "custom",
                             "edge_color": "#ff003c", "flash_color": "#ff003c", "sparkle_color": "#00f0ff"}),
        Preset("Toxic", {"color_mode": "two_v", "color1": "#00ff2a", "color2": "#c8ff00", "edge_mode": "custom",
                         "edge_color": "#8a00ff", "flash_color": "#c8ff00", "sparkle_color": "#8a00ff"}),
        Preset("Party", {"color_mode": "rainbow", "idle_glow": 0, "edge_mode": "cycle", "flash_color": "#ffffff",
                         "beat_punch": True, "sparkles": True}),
        Preset("Minimal", {"color_mode": "single", "color1": "#ffffff", "idle_glow": 0, "edge_mode": "off",
                           "beat_flash": False, "beat_punch": False, "sparkles": False}),
    ]

    # sections a preset owns; anything else (Tuning) is the user's and survives preset changes
    PRESET_SECTIONS = ("Colours", "Edge lights", "Beats & sparkle")

    PEAK_HOLD = 0.35
    PEAK_GRAVITY = 14.0
    SPARKLE_LIFE = 0.18

    def __init__(self, layout: KeyboardLayout):
        super().__init__(layout)
        n = len(layout.KEY_COLS)
        self.n, self.rows = n, len(layout.KEY_ROWS)
        self.height = np.zeros(n)
        self.vel = np.zeros(n)
        self.peak = np.zeros(n)
        self.peak_age = np.zeros(n)
        self.peak_vel = np.zeros(n)
        self.sparkles = {}
        self.flash = self.punch = 0.0
        self.cycle_hue = 0.0
        self.upper_keys = [cell for cell in layout.key_cells if cell[0] in layout.KEY_ROWS[:2]]

    # colour of bar column i at row k (0 = bottom), full brightness
    def _palette(self, s):
        mode = s["color_mode"]
        n, rows = self.n, self.rows
        c1, c2, c3 = (hex_to_rgb(s[k]) for k in ("color1", "color2", "color3"))
        shift = s["rainbow_shift"] / 360.0
        grid = []
        for i in range(n):
            col = []
            for k in range(rows):
                tx, ty = i / (n - 1), k / (rows - 1)
                if mode == "rainbow":
                    col.append(hsv(shift + 0.78 * tx + k * 0.012, 1, 1))
                elif mode == "single":
                    col.append(c1)
                elif mode == "two_h":
                    col.append(mix(c1, c2, tx))
                elif mode == "two_v":
                    col.append(mix(c1, c2, ty))
                else:
                    col.append(mix(c1, c2, ty * 2) if ty < 0.5 else mix(c2, c3, (ty - 0.5) * 2))
            grid.append(col)
        return grid

    def render(self, ctx: RenderContext, s: dict) -> list:
        L = self.layout
        dt, r = ctx.dt, ctx.audio
        levels = r.levels if r is not None else np.zeros(self.n)
        loudness = r.loudness if r is not None else 0.0
        gravity = 8.0 * s["fall_speed"]

        # bars: snap up, fall with gravity
        target = levels * self.rows
        up = target > self.height
        self.height = np.where(up, self.height + (target - self.height) * 0.85, self.height)
        self.vel = np.where(up, 0.0, self.vel + gravity * dt)
        self.height = np.where(up, self.height, np.maximum(target, self.height - self.vel * dt))
        hit = self.height >= self.peak
        self.peak = np.where(hit, self.height, self.peak)
        self.peak_age = np.where(hit, 0.0, self.peak_age + dt)
        self.peak_vel = np.where(hit | (self.peak_age < self.PEAK_HOLD), 0.0, self.peak_vel + self.PEAK_GRAVITY * dt)
        self.peak = np.maximum(self.height, self.peak - self.peak_vel * dt)

        sparkle_rgb = hex_to_rgb(s["sparkle_color"])
        if r is not None and r.beat:
            self.flash = max(self.flash, r.beat)
            self.punch = max(self.punch, r.beat)
            self.cycle_hue += 0.07
        if r is not None and r.hat and s["sparkles"] and self.upper_keys:
            for _ in range(1 + int(r.hat * 3)):
                _, _, led = random.choice(self.upper_keys)
                self.sparkles[led] = 0.0
        self.flash *= math.exp(-dt * 9)
        self.punch *= math.exp(-dt * 7)
        self.cycle_hue += dt * 0.03

        pal = self._palette(s)
        idle = s["idle_glow"] / 100.0 * (0.6 + 0.4 * loudness)

        # edge colour
        weights = levels + 1e-3
        bar_mix = tuple(sum(pal[i][1][ch] * weights[i] for i in range(self.n)) / weights.sum() for ch in range(3))
        edge_mode = s["edge_mode"]
        if edge_mode == "cycle":
            edge_base = hsv(self.cycle_hue, 1, 1)
        elif edge_mode == "custom":
            edge_base = hex_to_rgb(s["edge_color"])
        else:
            edge_base = bar_mix
        bass = float(levels[:3].mean())
        breathe = 0.5 + 0.5 * math.sin(ctx.now * 1.6)
        glow = 0.06 + 0.04 * breathe * (1 - loudness) + 0.5 * bass * (0.4 + 0.6 * loudness)

        colors = [(0.0, 0.0, 0.0)] * L.led_count
        punch_rgb = scale(edge_base, 0.35 * self.punch) if s["beat_punch"] and self.punch > 0.02 else None
        for i, c in enumerate(L.KEY_COLS):
            for k in range(self.rows):
                led = L.at(L.KEY_ROWS[self.rows - 1 - k], c)
                if led == NO_LED:
                    continue
                fill = min(1.0, max(0.0, self.height[i] - k))
                base = pal[i][k]
                color = scale(base, 0.08 + 0.92 * fill) if fill > 0 else scale(base, idle)
                if punch_rgb:
                    color = add(color, punch_rgb)
                if s["peak_dots"] and int(self.peak[i]) == k and self.peak[i] > 0.5 and self.peak[i] - self.height[i] > 0.35:
                    color = mix(base, (255, 255, 255), 0.55)
                colors[led] = color

        for led, age in list(self.sparkles.items()):
            if age > self.SPARKLE_LIFE:
                del self.sparkles[led]
                continue
            colors[led] = mix(colors[led], sparkle_rgb, 1 - age / self.SPARKLE_LIFE)
            self.sparkles[led] = age + dt

        if edge_mode != "off":
            edge = scale(edge_base, glow)
            if s["beat_flash"]:
                edge = mix(edge, hex_to_rgb(s["flash_color"]), self.flash * 0.85)
            for led in L.edge_ring:
                colors[led] = edge
        return colors
