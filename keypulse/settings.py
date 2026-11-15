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
        self.load()

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

    def save(self):
        with self._lock:
            data = {"app": self.app, "effects": self.effects}
        try:
            paths.settings_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def effect(self, eid=None) -> dict:
        return self.effects[eid or self.app["effect"]]
