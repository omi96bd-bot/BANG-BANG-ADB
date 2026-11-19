"""Small custom widgets, colours and animation helpers (Tkinter only)."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

FONT = "Nirmala UI"
LIGHT = {"bg": "#eef2f6", "panel": "#ffffff", "side": "#101c2c", "side_t": "#9fb0c6", "side_on": "#1b3158",
         "ink": "#15212f", "mute": "#667689", "line": "#dde4ec", "acc": "#2f6bff", "acc_d": "#1e4fd6",
         "ok": "#12a150", "bad": "#d93a3a", "warn": "#c47a00", "chip": "#e8efff", "logbg": "#0c131b",
         "logfg": "#9fb0c6", "okbg": "#e3f6ea", "badbg": "#fde8e8"}
DARK = {"bg": "#0b121c", "panel": "#142030", "side": "#070d15", "side_t": "#8ea1ba", "side_on": "#13264a",
        "ink": "#e6edf6", "mute": "#8da0b8", "line": "#22344a", "acc": "#4c82ff", "acc_d": "#3a6be0",
        "ok": "#2fc178", "bad": "#ff6b6b", "warn": "#e0a030", "chip": "#1b2e52", "logbg": "#070d15",
        "logfg": "#9fb0c6", "okbg": "#12301f", "badbg": "#3a1b1f"}
P: dict[str, str] = dict(LIGHT)          # current palette (read at widget creation time)
_ANIM = {"on": True}


def set_theme(name: str) -> None:
    P.clear()
    P.update(DARK if name == "dark" else LIGHT)


def set_anim(on: bool) -> None:
    _ANIM["on"] = bool(on)


def anim_on() -> bool:
    return _ANIM["on"]


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def lerp(c1: str, c2: str, t: float) -> str:
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def alive(w: Any) -> bool:
    try:
        return bool(w.winfo_exists())
    except Exception:
        return False


def tween(widget: Any, steps: int, delay: int, fn: Callable[[float], None],
          done: Optional[Callable[[], None]] = None) -> None:
    """Call fn(t) with t going to 1.0 over `steps` frames. Instant when animations are off."""
    if not anim_on() or steps <= 1:
        fn(1.0)
        if done:
            done()
        return

    def frame(i: int) -> None:
        if not alive(widget):
            return
        fn(i / steps)
        if i < steps:
            widget.after(delay, frame, i + 1)
        elif done:
            done()

    frame(1)


def style_ttk(root: tk.Misc) -> None:
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".", font=(FONT, 10), background=P["bg"], foreground=P["ink"])
    for name in ("TFrame", "TLabel"):
        st.configure(name, background=P["bg"], foreground=P["ink"])
    st.configure("TCombobox", fieldbackground=P["panel"], background=P["panel"], foreground=P["ink"],
                 arrowcolor=P["mute"], bordercolor=P["line"], lightcolor=P["panel"], darkcolor=P["panel"], padding=6)
    st.map("TCombobox", fieldbackground=[("readonly", P["panel"])], foreground=[("readonly", P["ink"])])
    st.configure("TEntry", fieldbackground=P["panel"], foreground=P["ink"], bordercolor=P["line"], padding=6)
    st.configure("TSpinbox", fieldbackground=P["panel"], foreground=P["ink"], bordercolor=P["line"], arrowsize=12)
    st.configure("Vertical.TScrollbar", background=P["line"], troughcolor=P["panel"], bordercolor=P["panel"],
                 arrowcolor=P["mute"])
    root.option_add("*TCombobox*Listbox.background", P["panel"])
    root.option_add("*TCombobox*Listbox.foreground", P["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", P["acc"])
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))


class Btn(tk.Label):
    """Flat button with hover colour. kind: plain | primary | danger | ghost."""
    KINDS = {"plain": ("panel", "ink", "chip"), "primary": ("acc", "#ffffff", "acc_d"),
             "danger": ("panel", "bad", "badbg"), "ghost": ("bg", "ink", "chip")}

    def __init__(self, master: tk.Misc, text: str, command: Optional[Callable[[], None]] = None,
                 kind: str = "plain", size: int = 10, padx: int = 14, pady: int = 7) -> None:
        bgk, fgk, hovk = self.KINDS[kind]
        fg = fgk if fgk.startswith("#") else P[fgk]
        super().__init__(master, text=text, bg=P[bgk], fg=fg, font=(FONT, size, "bold"), padx=padx, pady=pady,
                         cursor="hand2", highlightthickness=1,
                         highlightbackground=P["acc"] if kind == "primary" else P["line"])
        self.kind, self.command, self.enabled = kind, command, True
        self._bg, self._hover, self._fg = P[bgk], P[hovk], fg
        self.bind("<Enter>", lambda _e: self.enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg if self.enabled else self._off_bg()))
        self.bind("<ButtonRelease-1>", self._release)

    def _off_bg(self) -> str:
        return lerp(self._bg, P["panel"], 0.55) if self.kind == "primary" else self._bg

    def _release(self, e: Any) -> None:
        if self.enabled and self.command and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.configure(fg=self._fg if on else P["mute"], bg=self._bg if on else self._off_bg(),
                       cursor="hand2" if on else "arrow")

    def set_text(self, text: str) -> None:
        self.configure(text=text)


class Toggle(tk.Canvas):
    W, H = 44, 24

    def __init__(self, master: tk.Misc, variable: tk.BooleanVar, command: Optional[Callable[[], None]] = None,
                 bg: Optional[str] = None) -> None:
        super().__init__(master, width=self.W, height=self.H, bg=bg or P["panel"], highlightthickness=0, cursor="hand2")
        self.var, self.command = variable, command
        self.t = 1.0 if variable.get() else 0.0
        self._draw()
        self.bind("<Button-1>", self._click)

    def _draw(self) -> None:
        self.delete("all")
        col = lerp(P["line"], P["acc"], self.t)
        h = self.H
        self.create_oval(0, 0, h, h, fill=col, outline=col)
        self.create_oval(self.W - h, 0, self.W, h, fill=col, outline=col)
        self.create_rectangle(h / 2, 0, self.W - h / 2, h, fill=col, outline=col)
        x = 3 + (self.W - h) * self.t
        self.create_oval(x, 3, x + h - 6, h - 3, fill="#ffffff", outline="#ffffff")

    def _click(self, _e: Any) -> None:
        new = not self.var.get()
        self.var.set(new)
        start, end = self.t, 1.0 if new else 0.0

        def step(t: float) -> None:
            self.t = start + (end - start) * t
            self._draw()

        tween(self, 6, 18, step)
        if self.command:
            self.command()


class Seg(tk.Frame):
    """Segmented choice (like radio buttons in a pill)."""

    def __init__(self, master: tk.Misc, options: list[tuple[str, str]], variable: tk.StringVar,
                 command: Optional[Callable[[], None]] = None, size: int = 10) -> None:
        super().__init__(master, bg=P["line"], padx=2, pady=2)
        self.var, self.command, self.labels = variable, command, {}
        for val, text in options:
            lb = tk.Label(self, text=text, font=(FONT, size, "bold"), padx=12, pady=4, cursor="hand2")
            lb.pack(side="left", padx=1)
            lb.bind("<Button-1>", lambda _e, v=val: self.pick(v))
            self.labels[val] = lb
        self.refresh()

    def refresh(self) -> None:
        for val, lb in self.labels.items():
            on = self.var.get() == val
            lb.configure(bg=P["acc"] if on else P["panel"], fg="#ffffff" if on else P["mute"])

    def pick(self, val: str) -> None:
        self.var.set(val)
        self.refresh()
        if self.command:
            self.command()


class Bar(tk.Canvas):
    """Smooth progress bar. set(percent, running) eases to the new value; running adds a moving shine."""

    def __init__(self, master: tk.Misc, height: int = 10, bg: Optional[str] = None) -> None:
        super().__init__(master, height=height, bg=bg or P["bg"], highlightthickness=0)
        self.value = self.target = 0.0
        self.running, self.phase, self._job = False, 0, None
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, pct: float, running: Optional[bool] = None) -> None:
        self.target = max(0.0, min(100.0, pct))
        if running is not None:
            self.running = running
        if not anim_on():
            self.value = self.target
        if self._job is None:
            self._loop()

    def _loop(self) -> None:
        self._job = None
        if not alive(self):
            return
        self.value += (self.target - self.value) * 0.25 if anim_on() else 0
        if abs(self.target - self.value) < 0.3:
            self.value = self.target
        self.phase += 14
        self._draw()
        if anim_on() and (self.running or self.value != self.target):
            self._job = self.after(40, self._loop)

    def _draw(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 2), max(self.winfo_height(), 2)
        self.create_rectangle(0, 0, w, h, fill=P["line"], outline=P["line"])
        fw = w * self.value / 100
        if fw < 1:
            return
        col = P["ok"] if (self.value >= 100 and not self.running) else P["acc"]
        self.create_rectangle(0, 0, fw, h, fill=col, outline=col)
        if self.running:
            x0 = (self.phase % (fw + 80)) - 60
            a, b = max(0, x0), min(fw, x0 + 60)
            if b > a:
                self.create_rectangle(a, 0, b, h, fill=lerp(col, "#ffffff", 0.45), outline="")


class Toast:
    """Small message that slides up in the bottom-right corner and goes away by itself."""

    def __init__(self, root: tk.Misc) -> None:
        self.root, self.lbl, self.job = root, None, None

    def show(self, text: str, kind: str = "info") -> None:
        if alive(self.lbl):
            self.lbl.destroy()
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
        bg = {"ok": P["ok"], "bad": P["bad"]}.get(kind, P["ink"])
        lbl = self.lbl = tk.Label(self.root, text=text, bg=bg, fg="#ffffff", font=(FONT, 11, "bold"), padx=18, pady=10)
        lbl.place(relx=1.0, rely=1.0, x=-20, y=4, anchor="se")
        tween(lbl, 7, 16, lambda t: lbl.place_configure(y=-20 + 24 * (1 - t)))
        self.job = self.root.after(2600, lambda: self._hide(lbl))

    def _hide(self, lbl: tk.Label) -> None:
        if not alive(lbl):
            return
        tween(lbl, 6, 16, lambda t: lbl.place_configure(y=-20 + 30 * t), lambda: lbl.destroy())


class Scroll(tk.Frame):
    """Vertical scroll area. Put children into .body"""

    def __init__(self, master: tk.Misc, bg: Optional[str] = None) -> None:
        bg = bg or P["panel"]
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.body = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e: Any) -> None:
        box = self.canvas.bbox("all")
        if box and box[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


class DropZone(tk.Canvas):
    """Dashed box with moving dashes and a bobbing arrow. Click runs the command."""

    def __init__(self, master: tk.Misc, title: str, sub: str, command: Callable[[], None]) -> None:
        super().__init__(master, height=100, bg=P["panel"], highlightthickness=0, cursor="hand2")
        self.title, self.sub, self.t, self.hot = title, sub, 0, False
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.after(80, self._tick)

    def _hover(self, on: bool) -> None:
        self.hot = on
        self.itemconfigure("r", outline=P["acc_d"] if on else P["acc"], fill=lerp(P["chip"], P["acc"], 0.08) if on else P["chip"])

    def _draw(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 40), max(self.winfo_height(), 40)
        self.create_rectangle(4, 4, w - 4, h - 4, fill=P["chip"], outline=P["acc"], width=2, dash=(8, 6), tags="r")
        self.create_text(w // 2, h // 2 - 26, text="⬇", font=(FONT, 15), fill=P["acc"], tags="ic")
        self.create_text(w // 2, h // 2 + 2, text=self.title, font=(FONT, 12, "bold"), fill=P["ink"])
        self.create_text(w // 2, h // 2 + 24, text=self.sub, font=(FONT, 9), fill=P["mute"])

    def _tick(self) -> None:
        if not alive(self):
            return
        if anim_on():
            self.t += 1
            w, h = max(self.winfo_width(), 40), max(self.winfo_height(), 40)
            try:
                self.itemconfigure("r", dashoffset=-self.t * 2)
                self.coords("ic", w // 2, h // 2 - 26 + 3 * math.sin(self.t / 4))
            except tk.TclError:
                pass
        self.after(80, self._tick)


def card(parent: tk.Misc, **kw: Any) -> tk.Frame:
    return tk.Frame(parent, bg=P["panel"], highlightthickness=1, highlightbackground=P["line"], **kw)
