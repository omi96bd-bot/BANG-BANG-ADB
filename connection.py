"""Connection page: which phones are connected + step-by-step ways to connect one."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Callable, Optional

from devices import Device
from i18n import T
from pairing import PairingService
from widgets import FONT, P, Btn, Scroll, alive, card, lerp, tween

if TYPE_CHECKING:
    from ui import App


class Steps(tk.Frame):
    """A list of steps. States: pending, info, active (spinner), done, fail."""
    SYMBOL = {"pending": ("○", "mute"), "info": ("●", "acc"), "done": ("✔", "ok"), "fail": ("✖", "bad")}
    SPIN = "◐◓◑◒"

    def __init__(self, parent: tk.Misc, texts: list[str]) -> None:
        super().__init__(parent, bg=P["panel"])
        self.icons: list[tk.Label] = []
        self.labels: list[tk.Label] = []
        self.states: list[str] = []
        self.frame, self._job = 0, None
        for text in texts:
            row = tk.Frame(self, bg=P["panel"])
            row.pack(fill="x", pady=3)
            ic = tk.Label(row, text="○", font=(FONT, 13, "bold"), bg=P["panel"], fg=P["mute"], width=2)
            ic.pack(side="left", anchor="n")
            lb = tk.Label(row, text=text, font=(FONT, 10), bg=P["panel"], fg=P["mute"], justify="left",
                          wraplength=680, anchor="w")
            lb.pack(side="left", fill="x", expand=True)
            self.icons.append(ic)
            self.labels.append(lb)
            self.states.append("pending")

    def set(self, i: int, state: str, text: Optional[str] = None) -> None:
        if not 0 <= i < len(self.icons):
            return
        if text is not None:
            self.labels[i].config(text=text)
        if self.states[i] == state:
            return
        self.states[i] = state
        ic, lb = self.icons[i], self.labels[i]
        if state == "active":
            ic.config(text=self.SPIN[self.frame % 4], fg=P["acc"])
            lb.config(fg=P["ink"], font=(FONT, 10, "bold"))
            self._spin()
            return
        sym, col = self.SYMBOL[state]
        ic.config(text=sym, fg=P[col])
        lb.config(fg=P["ink"] if state != "pending" else P["mute"], font=(FONT, 10))
        if state in ("done", "fail"):
            tween(ic, 6, 20, lambda t: ic.config(font=(FONT, int(13 + 5 * math.sin(math.pi * t)), "bold")))

    def active(self) -> Optional[int]:
        return next((i for i, s in enumerate(self.states) if s == "active"), None)

    def _spin(self) -> None:
        if self._job is not None:
            return

        def tick() -> None:
            self._job = None
            if not alive(self):
                return
            act = [i for i, s in enumerate(self.states) if s == "active"]
            if not act:
                return
            self.frame += 1
            for i in act:
                self.icons[i].config(text=self.SPIN[self.frame % 4])
            self._job = self.after(140, tick)

        self._job = self.after(140, tick)


class ConnectionPage(tk.Frame):
    METHODS = (("usb", "🔌", "USB cable", "Fastest and simplest"),
               ("qr", "🔳", "QR code", "Android 11+, same Wi-Fi"),
               ("code", "🔢", "Pairing code", "Wireless debugging"),
               ("tcp", "📶", "USB → Wi-Fi", "Then unplug the cable"))

    def __init__(self, app: "App", parent: tk.Misc) -> None:
        super().__init__(parent, bg=P["bg"])
        self.app = app
        self.method = ""
        self.photo: Any = None
        self.cache: Optional[list] = None
        self.dots: list[tuple[tk.Canvas, int]] = []
        self.pulse_i = 0
        self.steps: Optional[Steps] = None
        self.banner: Optional[tk.Label] = None
        self.extra: list[tk.Misc] = []
        self.qr_phase = 0
        self.tcp_running = False
        self.tcp_map: dict[str, Device] = {}
        self.tcp_var = tk.StringVar()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        sc = self.scroll = Scroll(self, bg=P["bg"])
        sc.grid(row=0, column=0, sticky="nsew")
        body = self.body = sc.body
        body.columnconfigure(0, weight=1)

        head = tk.Frame(body, bg=P["bg"])
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        tk.Label(head, text=T("Connection"), font=(FONT, 18, "bold"), bg=P["bg"], fg=P["ink"]).pack(side="left")
        for text, fn in ((T("Disconnect all"), lambda: self.task(T("Disconnecting"), lambda: app.devman.disconnect(None))),
                         (T("Reconnect saved phones"), lambda: self.task(T("Connecting"), app.devman.reconnect_saved)),
                         (T("Find phones"), lambda: self.task(T("Searching"), app.devman.find_phones))):
            Btn(head, text, fn).pack(side="right", padx=(6, 0))

        self.status_card = card(body)
        self.status_card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 14))
        tk.Label(self.status_card, text=T("Phones"), font=(FONT, 11, "bold"), bg=P["panel"], fg=P["ink"],
                 anchor="w").pack(fill="x", padx=16, pady=(12, 6))
        self.rows = tk.Frame(self.status_card, bg=P["panel"])
        self.rows.pack(fill="x")

        tk.Label(body, text=T("Add a phone: pick a way"), font=(FONT, 11, "bold"), bg=P["bg"], fg=P["ink"],
                 anchor="w").grid(row=2, column=0, sticky="ew", padx=24, pady=(4, 8))
        grid = tk.Frame(body, bg=P["bg"])
        grid.grid(row=3, column=0, sticky="ew", padx=24)
        self.cards: dict[str, tk.Frame] = {}
        for i, (key, icon, title, sub) in enumerate(self.METHODS):
            grid.columnconfigure(i, weight=1, uniform="m")
            c = card(grid, cursor="hand2")
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            for w in (tk.Label(c, text=icon, font=(FONT, 24), bg=P["panel"]),
                      tk.Label(c, text=T(title), font=(FONT, 11, "bold"), bg=P["panel"], fg=P["ink"]),
                      tk.Label(c, text=T(sub), font=(FONT, 9), bg=P["panel"], fg=P["mute"], wraplength=150)):
                w.pack(padx=10, pady=(10 if w.cget("text") == icon else 0, 8 if w.cget("fg") == P["mute"] else 0))
                w.bind("<Button-1>", lambda _e, k=key: self.select(k))
            c.bind("<Button-1>", lambda _e, k=key: self.select(k))
            c.bind("<Enter>", lambda _e, cc=c: cc.configure(highlightbackground=P["acc"]))
            c.bind("<Leave>", lambda _e, cc=c, k=key: cc.configure(
                highlightbackground=P["acc"] if k == self.method else P["line"]))
            self.cards[key] = c

        self.proc = card(body)
        self.proc.grid(row=4, column=0, sticky="ew", padx=24, pady=(14, 24))
        self.proc.grid_remove()
        self.after(150, self._pulse)

    # ------------------------------------------------------------ helpers
    def _ui(self, fn: Callable[[], None]) -> None:
        """Run fn in the UI thread (called from worker threads)."""
        self.app.events.put(("cb", lambda _r: fn(), None, None))

    def task(self, label: str, fn: Callable[[], Any]) -> None:
        self.app.toast.show(label + "…")

        def done(res: Any) -> None:
            text = res[1] if isinstance(res, tuple) else str(res)
            self.app.log(text, "ok")
            self.app.toast.show(text.strip().splitlines()[0] if text.strip() else label, "ok")

        self.app.bg(fn, done)

    def _head(self, title: str, sub: str) -> None:
        tk.Label(self.proc, text=title, font=(FONT, 13, "bold"), bg=P["panel"], fg=P["ink"], anchor="w").pack(
            fill="x", padx=18, pady=(16, 2))
        tk.Label(self.proc, text=sub, font=(FONT, 10), bg=P["panel"], fg=P["mute"], anchor="w", justify="left",
                 wraplength=720).pack(fill="x", padx=18, pady=(0, 8))

    def _steps(self, texts: list[str]) -> Steps:
        self.steps = Steps(self.proc, texts)
        self.steps.pack(fill="x", padx=18, pady=4)
        return self.steps

    def _make_banner(self) -> None:
        self.banner = tk.Label(self.proc, text="", font=(FONT, 12, "bold"), anchor="w", justify="left",
                               wraplength=700, padx=14, pady=10, bg=P["panel"])

    def say(self, text: str, kind: str = "info") -> None:
        b = self.banner
        if b is None or not alive(b):
            return
        fg, bg = {"ok": (P["ok"], P["okbg"]), "bad": (P["bad"], P["badbg"]),
                  "info": (P["acc"], P["chip"])}.get(kind, (P["acc"], P["chip"]))
        if b.cget("text") == text:
            return
        b.config(text=text, fg=fg)
        if not b.winfo_ismapped():
            b.pack(fill="x", padx=18, pady=(6, 16))
        start = b.cget("bg")
        tween(b, 6, 24, lambda t: b.config(bg=lerp(start, bg, t)))

    def select(self, method: str) -> None:
        self.method = method
        for k, c in self.cards.items():
            c.configure(highlightbackground=P["acc"] if k == method else P["line"],
                        highlightthickness=2 if k == method else 1)
        self.app.pairing.stop()
        for w in self.proc.winfo_children():
            w.destroy()
        self.photo, self.qr_phase, self.steps, self.extra = None, 0, None, []
        self.proc.grid()
        self._make_banner()
        {"usb": self._usb, "qr": self._qr, "code": self._code, "tcp": self._tcp}[method]()
        self.update_idletasks()
        self.after(60, lambda: self.scroll.canvas.yview_moveto(1.0))

    def _btn(self, text: str, cmd: Callable[[], None], kind: str = "primary") -> Btn:
        b = Btn(self.proc, text, cmd, kind)
        b.pack(anchor="w", padx=18, pady=(8, 4))
        self.extra.append(b)
        return b

    # ------------------------------------------------------------ USB
    def _usb(self) -> None:
        self._head(T("Connect with a USB cable"), T("Each step turns green by itself when it is done."))
        s = self._steps([T("Turn on Developer options (Settings > About phone > tap Build number 7 times)"),
                         T("Turn ON USB debugging"), T("Connect the phone to the PC with a cable"),
                         T("Tap Allow on the phone screen"), T("Phone found")])
        self._usb_update(self.app.devices)

    def _usb_update(self, devs: list[Device]) -> None:
        s = self.steps
        if s is None:
            return
        usb = [d for d in devs if d.conn == "USB"]
        states = {d.state for d in usb}
        if not usb:
            s.set(0, "info"), s.set(1, "info"), s.set(2, "active"), s.set(3, "pending"), s.set(4, "pending")
            self.say(T("Waiting for a phone... (checks every 3 seconds)"), "info")
            return
        for i in (0, 1, 2):
            s.set(i, "done")
        if "device" in states:
            s.set(3, "done"), s.set(4, "done")
            self.say(T("Phone found ✔"), "ok")
        elif "unauthorized" in states:
            s.set(3, "active"), s.set(4, "pending")
            self.say(T("Tap Allow on the phone screen"), "bad")
        elif "offline" in states:
            s.set(3, "fail"), s.set(4, "pending")
            self.say(T("Phone is offline - unplug and replug the cable, then press Fix problems"), "bad")
        else:
            s.set(3, "active"), s.set(4, "pending")
            self.say(usb[0].reason or T("Waiting for the phone..."), "bad")

    # ------------------------------------------------------------ QR
    def _qr(self) -> None:
        self._head(T("Connect with a QR code (Wi-Fi)"),
                   T("The PC and the phone must be on the same Wi-Fi. Android 11 or newer."))
        s = self._steps([T("Phone: Settings > Developer options > Wireless debugging > turn ON"),
                         T("Tap \"Pair device with QR code\" on the phone"), T("Create the QR code here"),
                         T("Scan the QR code with the phone"), T("Pairing and connecting")])
        s.set(0, "info"), s.set(1, "info")
        missing = PairingService.missing_packages()
        if missing:
            s.set(2, "fail")
            self.say(T("To enable QR pairing, install: ") + "pip install " + " ".join(missing), "bad")
            return
        self._btn(T("Create QR code"), self._start_qr)
        self.qr_label = tk.Label(self.proc, bg=P["panel"])
        self.qr_label.pack(pady=4)
        self.extra.append(self.qr_label)

    def _start_qr(self) -> None:
        try:
            from PIL import ImageTk
            image = self.app.pairing.start()
            self.photo = ImageTk.PhotoImage(image.resize((240, 240)))
        except Exception as exc:
            self.steps.set(2, "fail")
            self.say(T("Could not create the QR: {err}", err=exc), "bad")
            return
        self.qr_label.config(image=self.photo)
        self.steps.set(2, "done"), self.steps.set(3, "active")
        self.qr_phase = 3
        self.say(T("Waiting for the QR scan... (60 seconds)"), "info")

    def on_pair_event(self, kind: str, text: str) -> None:
        s = self.steps
        if self.method != "qr" or s is None:
            return
        if kind == "status":
            if self.qr_phase == 3:
                s.set(3, "done"), s.set(4, "active")
                self.qr_phase = 4
            self.say(text, "info")
        elif kind == "ok":
            s.set(3, "done"), s.set(4, "done")
            self.say(text, "ok")
            self.photo = None
            lbl = getattr(self, "qr_label", None)
            if lbl is not None and alive(lbl):
                lbl.config(image="")
            self.app.devman.refresh_now()
            self.app.toast.show(T("Phone connected"), "ok")
        else:
            cur = s.active()
            s.set(cur if cur is not None else 3, "fail")
            self.say(text, "bad")
            self._btn(T("Use the pairing code method"), lambda: self.select("code"), "plain")

    # ------------------------------------------------------------ pairing code
    def _code(self) -> None:
        self._head(T("Connect with a pairing code (Wi-Fi)"),
                   T("Phone: Wireless debugging > \"Pair device with pairing code\". Type the IP:PORT and the 6-digit code it shows."))
        self._steps([T("Wireless debugging is ON (same Wi-Fi as this PC)"), T("Tap \"Pair device with pairing code\""),
                     T("Pair: enter the IP:PORT and the 6-digit code"), T("Connect: enter the IP:PORT from the main Wireless debugging screen")])
        self.steps.set(0, "info"), self.steps.set(1, "info"), self.steps.set(2, "info"), self.steps.set(3, "pending")
        self.pair_addr, self.pair_code, self.conn_addr = tk.StringVar(), tk.StringVar(), tk.StringVar()
        f = tk.Frame(self.proc, bg=P["panel"])
        f.pack(anchor="w", padx=18, pady=6)
        for r, (label, var, show) in enumerate(((T("Pair IP:PORT"), self.pair_addr, ""), (T("6-digit code"), self.pair_code, "*"),
                                                  (T("Connect IP:PORT"), self.conn_addr, ""))):
            tk.Label(f, text=label, bg=P["panel"], fg=P["ink"], font=(FONT, 10)).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=var, width=26, show=show).grid(row=r, column=1, padx=10, pady=4)
        Btn(f, T("Pair"), self._pair, "primary").grid(row=1, column=2, padx=4)
        Btn(f, T("Connect"), self._connect, "primary").grid(row=2, column=2, padx=4)

    def _pair(self) -> None:
        addr, code = self.pair_addr.get().strip(), self.pair_code.get().strip()
        self.pair_code.set("")
        if not addr or not code:
            self.say(T("Enter both the IP:PORT and the code."), "bad")
            return
        self.steps.set(2, "active")
        self.say(T("Pairing..."), "info")
        self.app.bg(lambda: self.app.adb.pair(addr, code), self._pair_done)

    def _pair_done(self, res: Any) -> None:
        ok = "Successfully paired" in res.text
        self.steps.set(2, "done" if ok else "fail")
        self.say(T("Pairing successful. Now enter the Connect IP:PORT and press Connect.") if ok
                 else T("Pairing failed: {err}", err=res.text), "ok" if ok else "bad")
        if ok:
            self.steps.set(3, "info")

    def _connect(self) -> None:
        addr = self.conn_addr.get().strip()
        if not addr:
            self.say(T("Enter the Connect IP:PORT."), "bad")
            return
        self.steps.set(3, "active")
        self.say(T("Connecting..."), "info")
        self.app.bg(lambda: self.app.adb.connect(addr), self._connect_done)

    def _connect_done(self, res: Any) -> None:
        ok = self.app.adb.is_connected(res)
        self.steps.set(3, "done" if ok else "fail")
        self.say(T("Connected ✔") if ok else T("Connect failed: {err}", err=res.text), "ok" if ok else "bad")
        self.app.devman.refresh_now()

    # ------------------------------------------------------------ USB -> Wi-Fi
    def _tcp(self) -> None:
        self._head(T("Switch a USB phone to Wi-Fi"), T("The phone must be plugged in with the cable and be on the same Wi-Fi as this PC."))
        self._steps([T("Keep the USB cable plugged in"), T("Read the phone's Wi-Fi address"),
                     T("Switch the phone to Wi-Fi mode (tcpip 5555)"), T("Connect over Wi-Fi"),
                     T("You can unplug the cable now")])
        self.steps.set(0, "info")
        f = tk.Frame(self.proc, bg=P["panel"])
        f.pack(anchor="w", padx=18, pady=6)
        tk.Label(f, text=T("Phone"), bg=P["panel"], fg=P["ink"], font=(FONT, 10)).pack(side="left")
        self.tcp_combo = ttk.Combobox(f, textvariable=self.tcp_var, state="readonly", width=44)
        self.tcp_combo.pack(side="left", padx=8)
        Btn(f, T("Start"), self._tcp_start, "primary").pack(side="left")
        self._tcp_refresh()

    def _tcp_refresh(self) -> None:
        if self.method != "tcp" or self.tcp_running or not alive(self.tcp_combo):
            return
        self.tcp_map = {f"{d.model or d.serial} · {d.serial}": d for d in self.app.devices if d.usable and d.conn == "USB"}
        labels = list(self.tcp_map)
        self.tcp_combo["values"] = labels
        if self.tcp_var.get() not in labels:
            self.tcp_var.set(labels[0] if labels else "")
        if not labels:
            self.say(T("Plug in a phone with a USB cable first."), "bad")
        elif self.banner is not None and self.banner.cget("text") == T("Plug in a phone with a USB cable first."):
            self.say(T("Ready. Press Start."), "info")

    def _tcp_start(self) -> None:
        dev = self.tcp_map.get(self.tcp_var.get())
        if not dev or self.tcp_running or self.steps is None:
            if not dev:
                self.say(T("Plug in a phone with a USB cable first."), "bad")
            return
        self.tcp_running = True
        s, serial, adb = self.steps, dev.serial, self.app.adb
        for i in range(1, 5):
            s.set(i, "pending")
        s.set(0, "done"), s.set(1, "active")
        self.say(T("Working..."), "info")

        def fail(step: int, msg: str) -> None:
            self.tcp_running = False
            s.set(step, "fail")
            self.say(msg, "bad")

        def work() -> None:
            ip = adb.wifi_ip(serial)
            if not ip:
                self._ui(lambda: fail(1, T("Could not read the phone's Wi-Fi address. Is the phone connected to Wi-Fi?")))
                return
            self._ui(lambda: (s.set(1, "done"), s.set(2, "active")))
            res = adb.tcpip(serial, 5555)
            if not res.ok:
                self._ui(lambda: fail(2, T("tcpip failed: {err}", err=res.text)))
                return
            self._ui(lambda: (s.set(2, "done"), s.set(3, "active")))
            time.sleep(2)
            addr, ok = f"{ip}:5555", False
            for _ in range(3):
                if adb.is_connected(adb.connect(addr)):
                    ok = True
                    break
                time.sleep(1.5)
            if not ok:
                self._ui(lambda: fail(3, T("Could not connect to {addr}. Check that the PC and phone are on the same Wi-Fi.", addr=addr)))
                return

            def good() -> None:
                self.tcp_running = False
                s.set(3, "done"), s.set(4, "done")
                self.say(T("Connected over Wi-Fi: {addr}. You can unplug the cable now.", addr=addr), "ok")
                self.app.devman.refresh_now()
                self.app.toast.show(T("Phone connected"), "ok")

            self._ui(good)

        self.app.bg(work)

    # ------------------------------------------------------------ phone status list
    def on_devices(self, devs: list[Device]) -> None:
        live = {d.serial for d in devs} | {a for d in devs for a in d.alts}
        data: list[tuple] = []
        for d in devs:
            data.append((d.key, d.model or d.serial, d.conn, d.serial, d.usable, "" if d.usable else d.reason, ""))
        for p in self.app.settings.saved_phones():
            if p.get("addr") not in live and not any(d.key == p.get("key") for d in devs):
                data.append((p.get("key", ""), p.get("name", "?"), "Wi-Fi", p.get("addr", ""), False,
                             T("Offline"), p.get("addr", "")))
        if data != self.cache:
            self.cache = data
            self._build_rows(data)
        if self.method == "usb":
            self._usb_update(devs)
        elif self.method == "tcp":
            self._tcp_refresh()

    def _build_rows(self, data: list[tuple]) -> None:
        for w in self.rows.winfo_children():
            w.destroy()
        self.dots = []
        if not data:
            tk.Label(self.rows, text=T("No phone is connected yet. Pick a way below."), bg=P["panel"], fg=P["mute"],
                     font=(FONT, 10), pady=14).pack()
            return
        for n, (key, name, conn, serial, usable, reason, saved) in enumerate(data):
            if n:
                tk.Frame(self.rows, height=1, bg=P["line"]).pack(fill="x")
            row = tk.Frame(self.rows, bg=P["panel"])
            row.pack(fill="x", padx=16, pady=8)
            dot = tk.Canvas(row, width=16, height=16, bg=P["panel"], highlightthickness=0)
            oval = dot.create_oval(3, 3, 13, 13, fill=P["ok"] if usable else P["bad"], outline="")
            dot.pack(side="left", padx=(0, 10))
            if usable:
                self.dots.append((dot, oval))
            info = tk.Frame(row, bg=P["panel"])
            info.pack(side="left")
            top = tk.Frame(info, bg=P["panel"])
            top.pack(anchor="w")
            tk.Label(top, text=name, font=(FONT, 10, "bold"), bg=P["panel"], fg=P["ink"]).pack(side="left")
            tk.Label(top, text=conn, font=(FONT, 8, "bold"), bg=P["chip"], fg=P["acc"], padx=6).pack(side="left", padx=6)
            tk.Label(info, text=serial, font=(FONT, 9), bg=P["panel"], fg=P["mute"]).pack(anchor="w")
            if saved:
                Btn(row, T("Reconnect"), lambda a=saved: self._reconnect(a), "primary", pady=4).pack(side="right")
            elif usable and conn == "Wi-Fi":
                Btn(row, T("Disconnect"), lambda s=serial: self._disconnect(s), "plain", pady=4).pack(side="right", padx=(8, 0))
            tk.Label(row, text=T("Connected ✔") if usable else reason, font=(FONT, 10, "bold"), bg=P["panel"],
                     fg=P["ok"] if usable else P["bad"], wraplength=360, justify="right").pack(side="right", padx=10)

    def _reconnect(self, addr: str) -> None:
        self.app.toast.show(T("Connecting") + "…")

        def done(res: Any) -> None:
            ok = self.app.adb.is_connected(res)
            self.app.toast.show(T("Phone connected") if ok else T("Connect failed: {err}", err=res.text), "ok" if ok else "bad")
            self.app.devman.refresh_now()

        self.app.bg(lambda: self.app.adb.connect(addr), done)

    def _disconnect(self, serial: str) -> None:
        self.app.bg(lambda: self.app.devman.disconnect([serial]), lambda r: self.app.toast.show(str(r).splitlines()[0] if str(r) else ""))

    def _pulse(self) -> None:
        if not alive(self):
            return
        self.pulse_i += 1
        k = (math.sin(self.pulse_i / 4) + 1) / 2
        for dot, oval in self.dots:
            if alive(dot):
                dot.itemconfigure(oval, fill=lerp(P["ok"], P["panel"], 0.55 * k))
        self.after(120, self._pulse)
