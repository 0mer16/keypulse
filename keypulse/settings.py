"""User settings, saved as JSON in %APPDATA%\\KeyPulse\\settings.json."""
import json
import threading

from . import paths
from .effects import EFFECTS

APP_DEFAULTS = {
    "effect": "visualizer",
    "brightness": 100,
    "start_on_launch": True,
}


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self.app = dict(APP_DEFAULTS)
        self.effects = {eid: cls.defaults() for eid, cls in EFFECTS.items()}
        self.user_presets = {eid: [] for eid in EFFECTS}     # eid -> [{"name": str, "values": dict}]
        self.load()

    # ---------- user presets ----------
    def presets_for(self, eid):
        """Built-in presets followed by the user's own (marked user=True)."""
        from .effects.base import Preset
        cls = EFFECTS[eid]
        mine = [Preset(p["name"], p["values"], user=True) for p in self.user_presets.get(eid, [])]
        return list(cls.presets) + mine

    def save_user_preset(self, eid, name):
        cls = EFFECTS[eid]
        keys = {c.key for c in cls.controls if c.section in cls.user_preset_sections()}
        values = {k: v for k, v in self.effects[eid].items() if k in keys}
        lst = self.user_presets.setdefault(eid, [])
        lst[:] = [p for p in lst if p["name"].lower() != name.lower()] + [{"name": name, "values": values}]
        self.save()

    def delete_user_preset(self, eid, name):
        self.user_presets[eid] = [p for p in self.user_presets.get(eid, []) if p["name"] != name]
        self.save()

    def load(self):
        f = paths.settings_file()
        if not f.exists():
            return
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.app.update({k: v for k, v in data.get("app", {}).items() if k in APP_DEFAULTS})
        for eid, values in data.get("effects", {}).items():
            if eid in self.effects:
                self.effects[eid].update({k: v for k, v in values.items() if k in self.effects[eid]})
                EFFECTS[eid].migrate(self.effects[eid])
        for eid, lst in data.get("user_presets", {}).items():
            if eid in self.effects and isinstance(lst, list):
                valid = set(self.effects[eid])
                self.user_presets[eid] = [
                    {"name": str(p["name"]), "values": {k: v for k, v in p.get("values", {}).items() if k in valid}}
                    for p in lst if isinstance(p, dict) and p.get("name")]

    def save(self):
        with self._lock:
            data = {"app": self.app, "effects": self.effects, "user_presets": self.user_presets}
        try:
            paths.settings_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def effect(self, eid=None) -> dict:
        return self.effects[eid or self.app["effect"]]
