"""Screenshot a window by title: python tools/screenshot.py KeyPulse out.png"""
import ctypes
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

user32 = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)

title, out = sys.argv[1], sys.argv[2]
hwnd = user32.FindWindowW(None, title)
if not hwnd:
    sys.exit(f"window {title!r} not found")
user32.ShowWindow(hwnd, 9)
user32.SetForegroundWindow(hwnd)
time.sleep(0.8)
rect = wintypes.RECT()
ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))  # frame bounds
ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(out)
print("saved", out, rect.right - rect.left, "x", rect.bottom - rect.top)
