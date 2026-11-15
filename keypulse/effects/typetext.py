"""Type to Light: whatever you type in the app is spelled out on the keyboard's own keys."""
import math

from .base import Control, Effect, KeyboardLayout, Preset, RenderContext, hex_to_rgb, hsv, mix, scale
from .keymap import led_for

STYLES = [("spell", "Spell it out (one letter at a time)"),
          ("typewriter", "Typewriter (letters build up the word)"),
          ("neon", "Neon sign (whole word glows)")]
COLOR_MODES = [("single", "One colour"), ("two", "Two colours: first → last letter"), ("rainbow", "Rainbow letters")]
EDGE_MODES = [("match", "Match the letter"), ("custom", "Custom colour"), ("off", "Off")]

_style = lambda *styles: (lambda s: s.get("style") in styles)


class TypeTextEffect(Effect):
    id = "typetext"
    name = "Type to Light"
    description = "Type a word or message and watch it light up on the keys."
    uses_audio = False

    controls = [
        Control("text", "Your text", "text", "HELLO", "Text",
                help="Letters, numbers and symbols on the keyboard. Spaces become short pauses."),

        Control("style", "Style", "choice", "spell", "Animation", options=STYLES),
        Control("speed", "Speed", "slider", 3, "Animation", min=0.5, max=10, step=0.5, suffix=" letters/s"),
        Control("pause", "Pause before repeating", "slider", 1.0, "Animation", min=0, max=4, step=0.25, suffix=" s"),
        Control("trail", "Letter trail", "slider", 30, "Animation", min=0, max=100, step=5, suffix="%",
                visible_if=_style("spell")),

        Control("color_mode", "Letter colours", "choice", "single", "Colours", options=COLOR_MODES),
        Control("color1", "Colour 1", "color", "#00e5ff", "Colours",
                visible_if=lambda s: s.get("color_mode") in ("single", "two")),
        Control("color2", "Colour 2", "color", "#ff00c8", "Colours",
                visible_if=lambda s: s.get("color_mode") == "two"),

        Control("bg_level", "Other keys glow", "slider", 4, "Background & edges", min=0, max=30, suffix="%"),
        Control("bg_color", "Other keys colour", "color", "#7a5cff", "Background & edges",
                visible_if=lambda s: s.get("bg_level", 0) > 0),
        Control("edge_mode", "Edge lights", "choice", "match", "Background & edges", options=EDGE_MODES),
        Control("edge_color", "Edge colour", "color", "#7a5cff", "Background & edges",
                visible_if=lambda s: s.get("edge_mode") == "custom"),
    ]

    presets = [
        Preset("Neon sign", {"style": "neon", "color_mode": "single", "color1": "#ff2e88", "bg_level": 0,
                             "edge_mode": "match"}),
        Preset("Rainbow spell", {"style": "spell", "speed": 3, "trail": 50, "color_mode": "rainbow",
                                 "bg_level": 3, "bg_color": "#ffffff", "edge_mode": "match"}),
        Preset("Typewriter", {"style": "typewriter", "speed": 4, "color_mode": "single", "color1": "#00ff41",
                              "bg_level": 6, "bg_color": "#003b0f", "edge_mode": "custom", "edge_color": "#00a82b"}),
        Preset("Secret message", {"style": "spell", "speed": 1.5, "pause": 2.5, "trail": 0, "color_mode": "single",
                                  "color1": "#ffffff", "bg_level": 0, "edge_mode": "off"}),
        Preset("Fire", {"style": "typewriter", "speed": 5, "color_mode": "two", "color1": "#ff2a00",
                        "color2": "#ffd000", "bg_level": 5, "bg_color": "#3a0a00", "edge_mode": "match"}),
        Preset("Ocean", {"style": "neon", "color_mode": "two", "color1": "#0040ff", "color2": "#00ffd5",
                         "bg_level": 4, "bg_color": "#001a33", "edge_mode": "match"}),
    ]
    PRESET_SECTIONS = ("Animation", "Colours", "Background & edges")

    ATTACK = 0.12        # fraction of a letter's slot spent fading in
    RELEASE = 0.30       # fraction spent fading out (gives repeated letters a visible blink)

    def __init__(self, layout: KeyboardLayout):
        super().__init__(layout)
        self.text = None
        self.seq = []    # one LED index (or None for a pause) per character
        self.t = 0.0

    def _prepare(self, text):
        self.text = text
        self.seq = [led_for(ch, self.layout.key_leds) for ch in text]
        self.t = 0.0

    def _letter_colors(self, s):
        lit = [i for i, led in enumerate(self.seq) if led is not None]
        m = len(lit)
        c1, c2 = hex_to_rgb(s["color1"]), hex_to_rgb(s["color2"])
        out = {}
        for j, i in enumerate(lit):
            if s["color_mode"] == "rainbow":
                out[i] = hsv(j / max(m, 1), 1, 1)
            elif s["color_mode"] == "two":
                out[i] = mix(c1, c2, j / (m - 1) if m > 1 else 0)
            else:
                out[i] = c1
        return out

    def _envelope(self, local, step):
        """Brightness of a letter `local` seconds into its slot of length `step`."""
        a, r = self.ATTACK * step, self.RELEASE * step
        if local < 0 or local >= step:
            return 0.0
        if local < a:
            return local / a
        if local > step - r:
            return max(0.0, (step - local) / r)
        return 1.0

    def render(self, ctx: RenderContext, s: dict) -> list:
        L = self.layout
        if s["text"] != self.text:
            self._prepare(s["text"])
        self.t += ctx.dt
        colors = [(0.0, 0.0, 0.0)] * L.led_count

        bg = scale(hex_to_rgb(s["bg_color"]), s["bg_level"] / 100.0)
        if s["bg_level"] > 0:
            for _, _, led in L.key_cells:
                colors[led] = bg

        n = len(self.seq)
        level = {}       # led -> (brightness, colour); the brightest wins when a key repeats
        edge_rgb, edge_v = (0.0, 0.0, 0.0), 0.0
        if n:
            step = 1.0 / s["speed"]
            letter_rgb = self._letter_colors(s)
            style = s["style"]

            def light(i, v, col):
                led = self.seq[i]
                if led is not None and v > level.get(led, (0, None))[0]:
                    level[led] = (v, col)

            if style == "neon":
                period = n * step + s["pause"]
                t = self.t % period
                sweep = t / step               # a soft highlight travels along the word
                for i in range(n):
                    if self.seq[i] is None:
                        continue
                    shimmer = 0.78 + 0.12 * math.sin(self.t * 2.4 + i * 1.7)
                    boost = max(0.0, 1 - abs(sweep - i - 0.5)) * 0.35
                    col = mix(letter_rgb[i], (255, 255, 255), boost * 0.5)
                    light(i, min(1.0, shimmer + boost), col)
                edge_rgb, edge_v = letter_rgb[next(iter(letter_rgb))] if letter_rgb else (0, 0, 0), 0.35
            elif style == "typewriter":
                hold = max(0.6, s["pause"])
                fade = 0.5
                period = n * step + hold + fade
                t = self.t % period
                out = 1.0 if t < n * step + hold else max(0.0, 1 - (t - n * step - hold) / fade)
                for i in range(n):
                    local = t - i * step
                    if local < 0 or self.seq[i] is None:
                        continue
                    v = min(1.0, local / (self.ATTACK * step)) * out
                    light(i, v, letter_rgb[i])
                    if local < step:           # the newest letter drives the edge
                        edge_rgb, edge_v = letter_rgb[i], v
                if t >= n * step:
                    last = max(letter_rgb) if letter_rgb else None
                    if last is not None:
                        edge_rgb, edge_v = letter_rgb[last], out
            else:  # spell
                period = n * step + s["pause"]
                t = self.t % period
                current = int(t // step) if t < n * step else None
                trail = s["trail"] / 100.0
                for i in range(n):
                    if self.seq[i] is None:
                        continue
                    local = t - i * step
                    v = self._envelope(local, step)
                    if v == 0 and trail > 0 and local >= step:
                        # fading afterglow, but never on the key that is about to light again
                        if current is None or self.seq[current] != self.seq[i]:
                            v = 0.6 * trail * math.exp(-(local - step) / (0.35 + trail))
                    if v > 0:
                        light(i, v, letter_rgb[i])
                    if i == current:
                        edge_rgb, edge_v = letter_rgb[i], v

        for led, (v, col) in level.items():
            colors[led] = mix(colors[led], col, 1.0) if v >= 1 else \
                tuple(b + (c - b) * v for b, c in zip(colors[led], col))

        if s["edge_mode"] != "off":
            if s["edge_mode"] == "custom":
                edge = scale(hex_to_rgb(s["edge_color"]), 0.15 + 0.35 * edge_v)
            else:
                edge = scale(edge_rgb, 0.08 + 0.42 * edge_v)
            for led in L.edge_ring:
                colors[led] = edge
        return colors
