"""Counts key presses anywhere in Windows, for effects that react to typing.

Privacy: this only reports *that* a key went down (and its virtual-key code, kept in memory for the
current frame). Nothing is logged, stored or sent anywhere. Presses made while KeyPulse's own window
is in front are ignored, so typing into the app doesn't trigger effects.

It polls GetAsyncKeyState for the typing keys ~125x per second instead of installing a keyboard hook,
which keeps it light and avoids looking like a keylogger to antivirus software.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

# typing keys only (no Shift/Ctrl/Alt/Win, so Shift+A counts once)
WATCHED = (
    [0x08, 0x09, 0x0D, 0x14, 0x1B, 0x20, 0x2E]          # backspace tab enter caps esc space delete
    + list(range(0x25, 0x29))                             # arrows
    + list(range(0x30, 0x3A)) + list(range(0x41, 0x5B))  # 0-9 A-Z
    + list(range(0xBA, 0xC1)) + list(range(0xDB, 0xDF))  # ; = , - . / `  [ \ ] '
)


def _own_window_in_front():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


class KeyWatcher:
    POLL = 0.008

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="KeyPulseKeys", daemon=True)
        self._thread.start()

    def _run(self):
        down = set()
        while not self._stop.is_set():
            now_down = {vk for vk in WATCHED if user32.GetAsyncKeyState(vk) & 0x8000}
            pressed = now_down - down
            down = now_down
            if pressed and not _own_window_in_front():
                with self._lock:
                    self._pending.extend(pressed)
            time.sleep(self.POLL)

    def drain(self):
        """Virtual-key codes pressed since the last call."""
        with self._lock:
            out, self._pending = self._pending, []
        return out

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
