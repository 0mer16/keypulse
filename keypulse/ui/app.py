"""KeyPulse desktop window (customtkinter)."""
import queue
import tkinter as tk
from tkinter import colorchooser, messagebox

import customtkinter as ctk

from .. import APP_NAME, __version__, paths
from ..effects import EFFECTS
from ..effects.base import KeyboardLayout, rgb_to_hex
from ..engine import Engine
from ..settings import Settings

ACCENT = "#7a5cff"
BG = "#121218"
PANEL = "#1b1b24"
CARD = "#23232f"
MUTED = "#8b8ba3"
STATE_COLORS = {"running": "#2ee59d", "starting": "#ffc94d", "error": "#ff5d6c", "stopped": "#6b6b80"}


class KeyboardPreview(tk.Canvas):
    """Mirrors the colours being sent to the keyboard: keys as squares, edge ring as thin strips."""

    KEY = 26
    GAP = 4
    EDGE = 7

    def __init__(self, master):
        L = KeyboardLayout
        w = self.EDGE * 2 + self.GAP * 2 + len(L.KEY_COLS) * (self.KEY + self.GAP) - self.GAP
        h = self.EDGE * 2 + self.GAP * 2 + len(L.KEY_ROWS) * (self.KEY + self.GAP) - self.GAP
        super().__init__(master, width=w, height=h, bg=PANEL, highlightthickness=0)
        self.items = {}   # (row, col) -> canvas item
        x0 = y0 = self.EDGE + self.GAP
        for r in L.KEY_ROWS:
            for c in L.KEY_COLS:
                x = x0 + (c - 1) * (self.KEY + self.GAP)
                y = y0 + (r - 1) * (self.KEY + self.GAP)
                self.items[(r, c)] = self.create_rectangle(x, y, x + self.KEY, y + self.KEY, fill="#222", width=0)
        cw = (w - 2 * self.EDGE) / (L.COLS - 2)
        for c in range(L.COLS):        # top and bottom strips
            x = self.EDGE + (c - 1) * cw if 0 < c < L.COLS - 1 else (0 if c == 0 else w - self.EDGE)
            x2 = x + (cw if 0 < c < L.COLS - 1 else self.EDGE)
            self.items[(0, c)] = self.create_rectangle(x, 0, x2, self.EDGE, fill="#222", width=0)
            self.items[(L.ROWS - 1, c)] = self.create_rectangle(x, h - self.EDGE, x2, h, fill="#222", width=0)
        rh = (h - 2 * self.EDGE) / (L.ROWS - 2)
        for r in range(1, L.ROWS - 1):  # side strips
            y = self.EDGE + (r - 1) * rh
            self.items[(r, 0)] = self.create_rectangle(0, y, self.EDGE, y + rh, fill="#222", width=0)
            self.items[(r, L.COLS - 1)] = self.create_rectangle(w - self.EDGE, y, w, y + rh, fill="#222", width=0)
        self.cache = {}

    def show(self, layout, colors):
        if not layout or not colors:
            return
        for r, c, led in layout.board_cells:
            item = self.items.get((r, c))
            if item is None or led >= len(colors):
                continue
            col = rgb_to_hex(tuple(max(v, 18) for v in colors[led]))
            if self.cache.get(item) != col:
                self.itemconfigure(item, fill=col)
                self.cache[item] = col


class SettingsPanel(ctk.CTkScrollableFrame):
    """Builds controls from an effect's schema and writes changes straight into its settings dict."""

    def __init__(self, master, on_change):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.on_change = on_change
        self.rows = []                 # (control or None for headers, widgets, advanced?)
        self.show_advanced = False
        self.columnconfigure(1, weight=1)

    def build(self, effect_cls, values):
        for child in self.winfo_children():
            child.destroy()
        self.rows, self.values, self.effect_cls = [], values, effect_cls
        self.adv_btn = None
        row = 0
        main = [c for c in effect_cls.controls if not c.advanced]
        adv = [c for c in effect_cls.controls if c.advanced]
        for group, is_adv in ((main, False), (adv, True)):
            if is_adv and group:
                self.adv_btn = ctk.CTkButton(self, text="", anchor="w", fg_color="transparent", hover_color=CARD,
                                             text_color=MUTED, height=32, command=self._toggle_advanced)
                self.adv_btn.grid(row=row, column=0, columnspan=2, sticky="w", pady=(18, 0))
                row += 1
            section = None
            for ctl in group:
                if ctl.section != section:
                    section = ctl.section
                    lbl = ctk.CTkLabel(self, text=section.upper(), text_color=MUTED,
                                       font=ctk.CTkFont(size=11, weight="bold"))
                    lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(16, 4))
                    self.rows.append((None, [lbl], is_adv))
                    row += 1
                label = ctk.CTkLabel(self, text=ctl.label, anchor="w")
                widget = self._widget(ctl, values)
                label.grid(row=row, column=0, sticky="w", padx=(4, 16), pady=5)
                widget.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
                self.rows.append((ctl, [label, widget], is_adv))
                row += 1
        self.refresh_visibility()

    def _toggle_advanced(self):
        self.show_advanced = not self.show_advanced
        self.refresh_visibility()

    def _widget(self, ctl, values):
        if ctl.kind == "choice" and not ctl.advanced and len(ctl.options) <= 4:
            # the main choices (pattern, colours) as one-click segmented buttons
            labels = [lab for _, lab in ctl.options]
            to_value = {lab: v for v, lab in ctl.options}
            seg = ctk.CTkSegmentedButton(self, values=labels, height=36, selected_color=ACCENT,
                                         selected_hover_color="#6247e0", unselected_color=CARD,
                                         unselected_hover_color="#2e2e3d", fg_color=CARD,
                                         command=lambda lab: self._set(ctl.key, to_value[lab]))
            seg.set(next((lab for v, lab in ctl.options if v == values[ctl.key]), labels[0]))
            return seg
        if ctl.kind == "choice":
            labels = [lab for _, lab in ctl.options]
            to_value = {lab: v for v, lab in ctl.options}
            current = next((lab for v, lab in ctl.options if v == values[ctl.key]), labels[0])
            menu = ctk.CTkOptionMenu(self, values=labels, fg_color=CARD, button_color=CARD,
                                     button_hover_color=ACCENT, dropdown_hover_color=ACCENT,
                                     command=lambda lab: self._set(ctl.key, to_value[lab]))
            menu.set(current)
            return menu
        if ctl.kind == "color":
            btn = ctk.CTkButton(self, text=values[ctl.key].upper(), fg_color=values[ctl.key], width=140,
                                hover=False, text_color=self._text_on(values[ctl.key]), corner_radius=8)

            def pick(b=btn, key=ctl.key):
                _, hexcol = colorchooser.askcolor(color=self.values[key], parent=self, title=ctl.label)
                if hexcol:
                    b.configure(fg_color=hexcol, text=hexcol.upper(), text_color=self._text_on(hexcol))
                    self._set(key, hexcol)
            btn.configure(command=pick)
            return btn
        if ctl.kind == "toggle":
            var = tk.BooleanVar(value=bool(values[ctl.key]))
            sw = ctk.CTkSwitch(self, text="", variable=var, progress_color=ACCENT,
                               command=lambda: self._set(ctl.key, var.get()))
            return sw
        if ctl.kind == "text":
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.columnconfigure(0, weight=1)
            var = tk.StringVar(value=values[ctl.key])
            entry = ctk.CTkEntry(frame, textvariable=var, height=40, font=ctk.CTkFont(size=18, weight="bold"),
                                 fg_color=CARD, border_color=ACCENT, placeholder_text="Type something…")
            entry.grid(row=0, column=0, sticky="ew")
            var.trace_add("write", lambda *_: self._set(ctl.key, var.get()[:60]))
            if ctl.help:
                ctk.CTkLabel(frame, text=ctl.help, text_color=MUTED, anchor="w",
                             font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", pady=(4, 0))
            return frame
        if ctl.kind == "slider":
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.columnconfigure(0, weight=1)
            val = ctk.CTkLabel(frame, width=56, anchor="e", text=f"{values[ctl.key]:g}{ctl.suffix}")
            steps = max(1, int(round((ctl.max - ctl.min) / ctl.step)))
            sl = ctk.CTkSlider(frame, from_=ctl.min, to=ctl.max, number_of_steps=steps, button_color=ACCENT,
                               progress_color=ACCENT,
                               command=lambda v: (val.configure(text=f"{round(v / ctl.step) * ctl.step:g}{ctl.suffix}"),
                                                  self._set(ctl.key, round(v / ctl.step) * ctl.step)))
            sl.set(values[ctl.key])
            sl.grid(row=0, column=0, sticky="ew")
            val.grid(row=0, column=1, padx=(8, 0))
            return frame
        raise ValueError(ctl.kind)

    @staticmethod
    def _text_on(hexcol):
        h = hexcol.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"

    def _set(self, key, value):
        self.values[key] = value
        self.refresh_visibility()
        self.on_change()

    def refresh_visibility(self):
        if getattr(self, "adv_btn", None) is not None:
            self.adv_btn.configure(text=("▾  Advanced settings" if self.show_advanced else "▸  Advanced settings"))
        for ctl, widgets, is_adv in self.rows:
            show = (self.show_advanced or not is_adv) and (ctl is None or ctl.visible_if is None
                                                           or ctl.visible_if(self.values))
            for w in widgets:
                w.grid() if show else w.grid_remove()


class KeyPulseApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.title(APP_NAME)
        self.geometry("1040x660+60+20")
        self.minsize(900, 560)
        try:
            self.iconbitmap(str(paths.resource("icon.ico")))
        except tk.TclError:
            pass

        self.settings = Settings()
        self.status_q = queue.Queue()
        self.engine = Engine(self.settings, on_status=lambda st, txt: self.status_q.put((st, txt)))
        self._save_job = None

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self.select_effect(self.settings.app["effect"])

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self._tick)
        if self.settings.app.get("start_on_launch", True):
            self.after(300, self.toggle_running)

    # ---------- layout ----------
    def _build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, width=250)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        ctk.CTkLabel(side, text=APP_NAME, font=ctk.CTkFont(size=26, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(22, 0))
        ctk.CTkLabel(side, text="for Mountain Everest 60", text_color=MUTED).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 18))
        ctk.CTkLabel(side, text="EFFECTS", text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=2, column=0, sticky="w", padx=20, pady=(4, 4))
        self.effect_buttons = {}
        r = 3
        for eid, cls in EFFECTS.items():
            b = ctk.CTkButton(side, text=cls.name, anchor="w", fg_color="transparent", hover_color=CARD,
                              corner_radius=8, height=36, command=lambda e=eid: self.select_effect(e))
            b.grid(row=r, column=0, sticky="ew", padx=12, pady=2)
            self.effect_buttons[eid] = b
            r += 1
        ctk.CTkLabel(side, text="More coming soon…", text_color=MUTED,
                     font=ctk.CTkFont(size=12, slant="italic")).grid(row=r, column=0, sticky="w", padx=20, pady=6)
        side.rowconfigure(r + 1, weight=1)

        ctk.CTkLabel(side, text="BRIGHTNESS", text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=r + 2, column=0, sticky="w", padx=20)
        self.brightness = ctk.CTkSlider(side, from_=5, to=100, number_of_steps=19, button_color=ACCENT,
                                        progress_color=ACCENT, command=self._on_brightness)
        self.brightness.set(self.settings.app["brightness"])
        self.brightness.grid(row=r + 3, column=0, sticky="ew", padx=16, pady=(4, 16))
        self.start_on_launch = tk.BooleanVar(value=self.settings.app["start_on_launch"])
        ctk.CTkSwitch(side, text="Auto-start lights", variable=self.start_on_launch,
                      progress_color=ACCENT, command=self._on_start_on_launch).grid(
            row=r + 4, column=0, sticky="w", padx=20, pady=(0, 12))
        ctk.CTkLabel(side, text=f"v{__version__}", text_color=MUTED).grid(row=r + 5, column=0, sticky="w",
                                                                         padx=20, pady=(0, 14))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=24, pady=18)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(top, text="●", font=ctk.CTkFont(size=18), text_color=STATE_COLORS["stopped"])
        self.status_dot.grid(row=0, column=0, padx=(0, 6))
        self.status_text = ctk.CTkLabel(top, text="Stopped", anchor="w")
        self.status_text.grid(row=0, column=1, sticky="w")
        self.fps_text = ctk.CTkLabel(top, text="", text_color=MUTED)
        self.fps_text.grid(row=0, column=2, padx=12)
        self.run_btn = ctk.CTkButton(top, text="Start", width=110, height=36, fg_color=ACCENT,
                                     hover_color="#6247e0", command=self.toggle_running)
        self.run_btn.grid(row=0, column=3)

        self.title_lbl = ctk.CTkLabel(main, text="", font=ctk.CTkFont(size=22, weight="bold"), anchor="w")
        self.title_lbl.grid(row=1, column=0, sticky="w", pady=(16, 0))
        self.desc_lbl = ctk.CTkLabel(main, text="", text_color=MUTED, anchor="w")
        self.desc_lbl.grid(row=2, column=0, sticky="w")

        card = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=14)
        card.grid(row=3, column=0, sticky="ew", pady=14)
        card.columnconfigure(0, weight=1)
        self.preview = KeyboardPreview(card)
        self.preview.grid(row=0, column=0, pady=(12, 8))
        self.preset_bar = ctk.CTkFrame(card, fg_color="transparent")
        self.preset_bar.grid(row=1, column=0, pady=(0, 10))

        self.panel = SettingsPanel(main, on_change=lambda: (self._mark_preset(None), self._changed()))
        self.panel.grid(row=4, column=0, sticky="nsew")

    # ---------- behaviour ----------
    def select_effect(self, eid):
        self.settings.app["effect"] = eid
        cls = EFFECTS[eid]
        for k, b in self.effect_buttons.items():
            b.configure(fg_color=CARD if k == eid else "transparent")
        self.title_lbl.configure(text=cls.name)
        self.desc_lbl.configure(text=cls.description)
        self._build_presets()
        self.panel.build(cls, self.settings.effect(eid))
        self._mark_preset(None)
        self._changed()

    def _build_presets(self, active=None):
        eid = self.settings.app["effect"]
        for child in self.preset_bar.winfo_children():
            child.destroy()
        self.preset_buttons = {}
        per_row = 8
        presets = self.settings.presets_for(eid)
        for i, p in enumerate(presets):
            b = ctk.CTkButton(self.preset_bar, text=("★ " if p.user else "") + p.name, width=80, height=26,
                              fg_color=CARD, hover_color=CARD, border_width=2, border_color=p.swatch,
                              corner_radius=13, font=ctk.CTkFont(size=12), command=lambda p=p: self.apply_preset(p))
            b.grid(row=i // per_row, column=i % per_row, padx=2, pady=2)
            if p.user:
                b.bind("<Button-3>", lambda e, p=p: self._delete_preset(p))
            self.preset_buttons[p.name] = b
        n = len(presets)
        ctk.CTkButton(self.preset_bar, text="＋ Save", width=80, height=26, fg_color="transparent",
                      hover_color=CARD, border_width=2, border_color=MUTED, text_color=MUTED, corner_radius=13,
                      font=ctk.CTkFont(size=12), command=self._save_preset).grid(
            row=n // per_row, column=n % per_row, padx=2, pady=2)
        self._mark_preset(active)

    def _save_preset(self):
        eid = self.settings.app["effect"]
        dialog = ctk.CTkInputDialog(text="Name your preset:", title="Save preset", button_fg_color=ACCENT,
                                    button_hover_color="#6247e0")
        name = (dialog.get_input() or "").strip()[:24]
        if not name:
            return
        builtin = {p.name.lower() for p in EFFECTS[eid].presets}
        if name.lower() in builtin:
            messagebox.showinfo(APP_NAME, f'"{name}" is a built-in preset name. Please pick another name.', parent=self)
            return
        existing = {p["name"].lower() for p in self.settings.user_presets.get(eid, [])}
        if name.lower() in existing and not messagebox.askyesno(
                APP_NAME, f'Replace your preset "{name}" with the current settings?', parent=self):
            return
        self.settings.save_user_preset(eid, name)
        self._build_presets(active=name)

    def _delete_preset(self, preset):
        if messagebox.askyesno(APP_NAME, f'Delete your preset "{preset.name}"?', parent=self):
            self.settings.delete_user_preset(self.settings.app["effect"], preset.name)
            self._build_presets()

    def apply_preset(self, preset):
        cls = EFFECTS[self.settings.app["effect"]]
        values = self.settings.effect()
        cls.apply_preset(values, preset)
        self.panel.build(cls, values)
        self._mark_preset(preset.name)
        self._changed()

    def _mark_preset(self, name):
        """Fill the chosen preset's button with its colour until a setting is changed by hand."""
        for pname, b in getattr(self, "preset_buttons", {}).items():
            if pname == name:
                sw = b.cget("border_color")
                b.configure(fg_color=sw, text_color=SettingsPanel._text_on(sw))
            else:
                b.configure(fg_color=CARD, text_color="#ffffff")

    def toggle_running(self):
        if self.engine.running:
            self.engine.stop()
            self.run_btn.configure(text="Start")
        else:
            self.engine.start()
            self.run_btn.configure(text="Stop")

    def _on_brightness(self, v):
        self.settings.app["brightness"] = int(v)
        self._changed()

    def _on_start_on_launch(self):
        self.settings.app["start_on_launch"] = self.start_on_launch.get()
        self._changed()

    def _changed(self):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(600, self.settings.save)

    def _tick(self):
        try:
            while True:
                state, text = self.status_q.get_nowait()
                self.status_dot.configure(text_color=STATE_COLORS.get(state, MUTED))
                self.status_text.configure(text=text)
        except queue.Empty:
            pass
        if self.engine.state == "running":
            self.fps_text.configure(text=f"{self.engine.fps:.0f} fps")
        else:
            self.fps_text.configure(text="")
        self.preview.show(self.engine.layout, self.engine.last_colors)
        self.after(50, self._tick)

    def on_close(self):
        self.settings.save()
        self.status_text.configure(text="Closing…")
        self.update_idletasks()
        self.engine.shutdown()
        self.destroy()
