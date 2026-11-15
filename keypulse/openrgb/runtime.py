"""Finds or starts an OpenRGB SDK server that can see the Everest 60.

Order of preference:
  1. An OpenRGB the user already runs with its SDK server on 6742 that sees the keyboard.
  2. The OpenRGB bundled with KeyPulse, started hidden on its own port with a private,
     keyboard-only configuration (so it never touches other RGB devices).
  3. A separately installed OpenRGB, started the same hidden way.
"""
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from .. import paths
from .client import OpenRGB

DEFAULT_PORT = 6742
OWN_PORT = 6744
KEYBOARD_DETECTORS = ("Mountain Everest 60",)
CREATE_NO_WINDOW = 0x08000000


def _port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _has_keyboard(port):
    try:
        c = OpenRGB(port=port, name="KeyPulse probe")
        try:
            c.find("Everest")
            return True
        finally:
            c.close()
    except (OSError, LookupError, ConnectionError):
        return False


def find_openrgb_exe():
    candidates = [paths.bundled_openrgb()]
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates += [Path(base) / "Programs" / "OpenRGB" / "OpenRGB.exe", Path(base) / "OpenRGB" / "OpenRGB.exe"]
    return next((p for p in candidates if p.is_file()), None)


def write_keyboard_only_config(config_dir: Path):
    """Enable only the Everest 60 detector: faster start-up, no warnings, other devices untouched."""
    names = json.loads(paths.resource("openrgb_detectors.json").read_text(encoding="utf-8"))
    detectors = {n: (n in KEYBOARD_DETECTORS) for n in names}
    cfg_file = config_dir / "OpenRGB.json"
    cfg = {}
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
    # OpenRGB adds any detector it doesn't find in the file as enabled, so list them all
    existing = cfg.get("Detectors", {}).get("detectors", {})
    for n in existing:
        detectors.setdefault(n, n in KEYBOARD_DETECTORS)
    cfg["Detectors"] = {"detectors": detectors}
    cfg_file.write_text(json.dumps(cfg, indent=1), encoding="utf-8")


class OpenRGBRuntime:
    def __init__(self, log=print):
        self.log = log
        self.proc = None
        self.port = None

    def ensure(self, timeout=20.0):
        """Return the port of a working SDK server that sees the keyboard. Raises RuntimeError if impossible."""
        if self.proc and self.proc.poll() is None and self.port and _has_keyboard(self.port):
            return self.port
        if _port_open(DEFAULT_PORT) and _has_keyboard(DEFAULT_PORT):
            self.log("Using your running OpenRGB")
            self.port = DEFAULT_PORT
            return self.port
        if _port_open(OWN_PORT) and _has_keyboard(OWN_PORT):
            self.port = OWN_PORT            # left over from a previous KeyPulse session
            return self.port

        exe = find_openrgb_exe()
        if not exe:
            raise RuntimeError("OpenRGB was not found. Reinstall KeyPulse (it ships with OpenRGB).")
        cfg = paths.openrgb_config_dir()
        write_keyboard_only_config(cfg)
        self.stop()
        self.log("Starting OpenRGB")
        self.proc = subprocess.Popen(
            [str(exe), "--server", "--server-port", str(OWN_PORT), "--noautoconnect", "--config", str(cfg)],
            cwd=str(exe.parent), creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        self.port = OWN_PORT
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("OpenRGB stopped unexpectedly while starting.")
            if _port_open(OWN_PORT):
                # the server opens before detection finishes; give it a moment to find the keyboard
                for _ in range(20):
                    if _has_keyboard(OWN_PORT):
                        return OWN_PORT
                    time.sleep(0.5)
                raise RuntimeError(
                    "OpenRGB is running but can't see the Everest 60. Check it's plugged in, close Base Camp, "
                    "and make sure its firmware has been updated once with Base Camp.")
            time.sleep(0.25)
        raise RuntimeError("OpenRGB didn't start in time.")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
