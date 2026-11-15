"""Shared pieces for effects: colour helpers, keyboard layout, settings schema, Effect base class."""
import colorsys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

NO_LED = 0xFFFFFFFF
RGB = tuple  # (r, g, b) floats 0..255


# ---------- colour helpers ----------
def hex_to_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def rgb_to_hex(c: RGB) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)


def hsv(h, s, v) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (r * 255, g * 255, b * 255)


def mix(c1: RGB, c2: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


def scale(c: RGB, k: float) -> RGB:
    return tuple(v * k for v in c)


def add(c1: RGB, c2: RGB) -> RGB:
    return tuple(min(255.0, a + b) for a, b in zip(c1, c2))


# ---------- keyboard layout ----------
class KeyboardLayout:
    """Everest 60 layout from OpenRGB's 7x23 matrix (columns 17-22 belong to the optional numpad)."""

    ROWS = 7
    COLS = 17
    KEY_ROWS = (1, 2, 3, 4, 5)       # top -> bottom
    KEY_COLS = tuple(range(1, 16))   # 15 key columns

    def __init__(self, matrix, led_count, led_names=None):
        self.matrix = matrix
        self.led_count = led_count
        self.led_names = list(led_names or [])
        # "Key: A" -> LED index, for effects that light specific keys
        self.key_leds = {n[5:] if n.startswith("Key: ") else n: i for i, n in enumerate(self.led_names)}

        def at(r, c):
            try:
                v = matrix[r][c]
            except IndexError:
                return NO_LED
            return v if v < led_count else NO_LED

        self.at = at
        # edge ring in clockwise order starting top-left, for effects that run around it
        ring = [(0, c) for c in range(self.COLS)] + [(r, self.COLS - 1) for r in range(1, self.ROWS - 1)] + \
               [(self.ROWS - 1, c) for c in reversed(range(self.COLS))] + [(r, 0) for r in reversed(range(1, self.ROWS - 1))]
        self.edge_ring = [at(r, c) for r, c in ring if at(r, c) != NO_LED]
        self.key_cells = [(r, c, at(r, c)) for r in self.KEY_ROWS for c in self.KEY_COLS if at(r, c) != NO_LED]
        self.board_cells = [(r, c, at(r, c)) for r in range(self.ROWS) for c in range(self.COLS)]


# ---------- settings schema ----------
@dataclass
class Control:
    key: str
    label: str
    kind: str                      # "choice" | "color" | "slider" | "toggle" | "text"
    default: Any
    section: str = "Settings"
    options: list = field(default_factory=list)       # choice: [(value, label)]
    min: float = 0
    max: float = 100
    step: float = 1
    suffix: str = ""
    visible_if: Optional[Callable[[dict], bool]] = None
    help: str = ""


@dataclass
class Preset:
    name: str
    values: dict

    @property
    def swatch(self) -> str:
        """A representative colour for the preset's button."""
        if self.values.get("color_mode", "rainbow") == "rainbow":
            return "#ff3df0"
        return self.values.get("color2") or self.values.get("color1") or "#ffffff"


@dataclass
class RenderContext:
    dt: float
    now: float
    audio: Any = None              # audio.features.Frame when the effect uses audio
    keys: list = field(default_factory=list)   # virtual-key codes pressed this frame (if the effect wants keys)


class Effect:
    id = "base"
    name = "Effect"
    description = ""
    uses_audio = False
    controls: list = []
    presets: list = []
    PRESET_SECTIONS: tuple = ()   # control sections a preset resets to defaults before applying

    def __init__(self, layout: KeyboardLayout):
        self.layout = layout

    def wants_keys(self, settings: dict) -> bool:
        """Whether the engine should watch for key presses (only while needed)."""
        return False

    @classmethod
    def defaults(cls) -> dict:
        return {c.key: c.default for c in cls.controls}

    @classmethod
    def apply_preset(cls, values: dict, preset: "Preset"):
        """Reset the preset-owned sections to defaults, then apply the preset (Tuning etc. is kept)."""
        for c in cls.controls:
            if c.section in cls.PRESET_SECTIONS:
                values[c.key] = c.default
        values.update(preset.values)

    def render(self, ctx: RenderContext, settings: dict) -> list:
        """Return one (r, g, b) per LED."""
        raise NotImplementedError
