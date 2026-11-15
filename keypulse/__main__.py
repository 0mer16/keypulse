"""Entry point: `python -m keypulse` or the packaged KeyPulse.exe."""
import ctypes
import logging
import sys

from . import APP_NAME, __version__, paths


def _single_instance():
    """Only one KeyPulse may drive the keyboard at a time."""
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KeyPulseSingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(paths.user_dir() / "keypulse.log", encoding="utf-8", mode="w")])
    logging.getLogger("keypulse").info("%s %s starting", APP_NAME, __version__)
    if not _single_instance():
        ctypes.windll.user32.MessageBoxW(None, f"{APP_NAME} is already running.", APP_NAME, 0x40)
        return
    from .ui.app import KeyPulseApp
    KeyPulseApp().mainloop()


if __name__ == "__main__":
    main()
