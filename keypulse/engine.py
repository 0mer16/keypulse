"""Background engine: keeps OpenRGB connected and renders the active effect to the keyboard."""
import logging
import threading
import time

from .audio.features import Features
from .audio.loopback import Loopback
from .effects import EFFECTS
from .effects.base import KeyboardLayout, RenderContext, hex_to_rgb, scale
from .openrgb.client import OpenRGB
from .openrgb.runtime import OpenRGBRuntime

log = logging.getLogger("keypulse.engine")


class Engine:
    FPS = 60

    def __init__(self, settings, on_status=None):
        self.settings = settings
        self.on_status = on_status or (lambda state, text: None)
        self.runtime = OpenRGBRuntime(log=lambda m: self._status("starting", m))
        self.layout = None
        self.last_colors = None          # latest frame, read by the UI preview
        self.fps = 0.0
        self._thread = None
        self._stop = threading.Event()
        self.state = "stopped"

    # ---------- control ----------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="KeyPulseEngine", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._status("stopped", "Stopped")

    def shutdown(self):
        self.stop()
        self.runtime.stop()

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _status(self, state, text):
        self.state = state
        log.info("%s: %s", state, text)
        self.on_status(state, text)

    # ---------- loop ----------
    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except Exception as e:  # keep the app alive; show the problem and retry
                log.exception("engine error")
                self._status("error", str(e) or e.__class__.__name__)
                self._stop.wait(3)

    def _session(self):
        self._status("starting", "Connecting to keyboard…")
        port = self.runtime.ensure()
        client = OpenRGB(port=port, name="KeyPulse")
        cap = None
        try:
            kb = client.find("Everest")
            self.layout = KeyboardLayout(kb.matrix, kb.led_count, kb.leds)
            client.direct_mode(kb)
            effect_id, effect, features = None, None, None
            self._status("running", f"Running on {kb.name}")
            frame_time = 1.0 / self.FPS
            last = time.perf_counter()
            frames, fps_t = 0, last
            while not self._stop.is_set():
                now = time.perf_counter()
                dt = min(0.1, max(1e-3, now - last))
                last = now

                eid = self.settings.app["effect"]
                if eid != effect_id:
                    effect_id, effect = eid, EFFECTS[eid](self.layout)
                if effect.uses_audio and cap is None:
                    cap = Loopback()
                    features = Features(cap.rate, len(self.layout.KEY_COLS))
                elif not effect.uses_audio and cap is not None:
                    cap.close()
                    cap = None
                s = self.settings.effect(eid)

                audio = None
                if effect.uses_audio:
                    features.gain = s.get("sensitivity", 100) / 100.0
                    try:
                        audio = features.update(cap.read(), dt)
                    except OSError:     # playback device changed (headphones etc.) - reopen
                        cap.close()
                        cap = None
                        continue

                colors = effect.render(RenderContext(dt=dt, now=time.time(), audio=audio), s)
                b = self.settings.app["brightness"] / 100.0
                if b < 0.999:
                    colors = [scale(c, b) for c in colors]
                client.set_colors(kb, colors)
                self.last_colors = colors

                frames += 1
                if now - fps_t >= 1.0:
                    self.fps = frames / (now - fps_t)
                    frames, fps_t = 0, now
                # time.sleep is high-resolution on Windows (Python 3.11+); Event.wait is ~15.6 ms coarse
                time.sleep(max(0.0, frame_time - (time.perf_counter() - now)))

            # stopped by the user: leave a soft static glow instead of a frozen frame
            try:
                glow = scale(hex_to_rgb(self.settings.effect().get("color1", "#00e5ff")), 0.25)
                client.set_colors(kb, [glow] * kb.led_count)
                self.last_colors = [glow] * kb.led_count
            except OSError:
                pass
        finally:
            if cap:
                cap.close()
            client.close()
