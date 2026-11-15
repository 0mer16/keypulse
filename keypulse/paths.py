"""Where KeyPulse finds its bundled files and keeps the user's settings."""
import os
import sys
from pathlib import Path

from . import APP_NAME


def bundle_dir() -> Path:
    """Folder holding bundled resources (PyInstaller's _internal, or the repo root when run from source)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource(*parts) -> Path:
    return Path(__file__).resolve().parent.joinpath("resources", *parts) if not getattr(sys, "frozen", False) \
        else bundle_dir().joinpath("keypulse", "resources", *parts)


def user_dir() -> Path:
    if getattr(sys, "frozen", False):
        d = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    else:
        # Running from source: keep data in the repo. (Microsoft Store Python silently redirects
        # AppData into a sandbox that the OpenRGB child process can't see.)
        d = bundle_dir() / ".keypulse-data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_file() -> Path:
    return user_dir() / "settings.json"


def openrgb_config_dir() -> Path:
    d = user_dir() / "openrgb"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundled_openrgb() -> Path:
    if getattr(sys, "frozen", False):
        return bundle_dir() / "OpenRGB" / "OpenRGB.exe"
    return bundle_dir() / "vendor" / "OpenRGB" / "OpenRGB.exe"   # fetched by build.ps1
