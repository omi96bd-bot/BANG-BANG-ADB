"""Add-phone wizard (USB / QR / pairing code), wireless tools and brand help window."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Optional

from devices import Device
from help_text import BRANDS
from pairing import PairingService

if TYPE_CHECKING:
    from ui import App

FONT = "Nirmala UI"
GREEN, RED, GRAY = "#1b7f3b", "#c62828", "#6b7280"
USB_STEPS = (
    "Turn on Developer options (Settings > About phone > tap Build number 7 times)",
    "Turn ON USB debugging",
    "Connect the phone to the PC with a cable",
    "Tap Allow on the phone screen",
)


def show_brand_help(app: "App", brand: str) -> None:
    """Popup with setup steps; the combobox lets the user switch brand."""
    win = tk.Toplevel(app.root)
    win.title("Phone setup help")
    win.geometry("560x420")
    win.transient(app.root)
    names = {k: v[0] for k, v in BRANDS.items()}
    chosen = tk.StringVar(value=names.get(brand, names["generic"]))
    top = ttk.Frame(win, padding=10)
    top.pack(fill="x")
    ttk.Label(top, text="Brand:", font=(FONT, 10, "bold")).pack(side="left")
    combo = ttk.Combobox(top, values=list(names.values()), textvariable=chosen, state="readonly", width=32)
    combo.pack(side="left", padx=8)
    body = tk.Text(win, wrap="word", font=(FONT, 11), padx=12, pady=8, relief="flat", bg="#ffffff")
    body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def fill(*_: Any) -> None:
        key = next((k for k, v in names.items() if v == chosen.get()), "generic")
        body.config(state="normal")
        body.delete("1.0", "end")
        for i, step in enumerate(BRANDS[key][1], 1):
            body.insert("end", f"{i}. {step}\n\n")
        body.config(state="disabled")

    combo.bind("<<ComboboxSelected>>", fill)
    fill()


def build_wireless_tools(app: "App", parent: tk.Misc) -> ttk.Frame:
    """Switch USB->Wi-Fi, Find phones, Reconnect saved, Disconnect. Shared by wizard and Wireless tab."""
    frame = ttk.Frame(parent, padding=8)
    out = tk.StringVar(value="")

    def show(text: Any) -> None:
        out.set(text[1] if isinstance(text, tuple) else str(text))

    def task(label: str, fn: Any) -> None:
        out.set(label + "…")
        app.bg(fn, show)

    def switch() -> None:
        dev = app.pick_usb_device()
        if dev:
            task("Switching to Wi-Fi", lambda: app.devman.switch_to_wifi(dev.serial))

    def disconnect_ticked() -> None:
        serials = [d.serial for d in app.devices if d.conn == "Wi-Fi" and d.key in app.checked]
        task("Disconnecting", lambda: app.devman.disconnect(serials))

    buttons = (
        ("Switch USB phone to Wi-Fi", switch),
        ("Find phones", lambda: task("Searching", app.devman.find_phones)),
        ("Reconnect saved phones", lambda: task("Connecting", app.devman.reconnect_saved)),
        ("Disconnect selected Wi-Fi phones", disconnect_ticked),
        ("Disconnect all", lambda: task("Disconnecting", lambda: app.devman.disconnect(None))),
    )
    for i, (text, cmd) in enumerate(buttons):
        ttk.Button(frame, text=text, command=cmd).grid(row=i, column=0, sticky="ew", pady=3)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, textvariable=out, wraplength=520, justify="left", font=(FONT, 10, "bold")).grid(
        row=len(buttons), column=0, sticky="w", pady=8)
    notes = (
        "When finished, turn Wireless debugging OFF on the phone - while it is on, the phone is open on the local network.",
        "If AP/Client isolation is on in the router, phones cannot be found.",
        "The Wireless debugging port changes, so Reconnect also looks for the new port using mDNS.",
    )
    for note in notes:
        ttk.Label(frame, text="• " + note, wraplength=520, justify="left", foreground=GRAY).grid(
            row=len(buttons) + 1 + notes.index(note), column=0, sticky="w")
    return frame


class Wizard:
    def __init__(self, app: "App") -> None:
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Add phone")
        self.win.geometry("700x640")
        self.win.transient(app.root)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.photo: Any = None
        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self._usb_tab()
        self.missing = PairingService.missing_packages()
        self.qr_tab: Optional[ttk.Frame] = None
        if not self.missing:
            self._qr_tab()
        self._code_tab()
        self.nb.add(build_wireless_tools(app, self.nb), text="More")
        if self.missing:
            ttk.Label(self.win, text="To enable QR pairing, install: pip install " + " ".join(self.missing),
                      foreground=GRAY).pack(pady=(0, 8))
        self.on_devices(app.devices)

    # ---------- USB ----------
    def _usb_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=14)
        self.nb.add(tab, text="USB cable")
        ttk.Label(tab, text="Each step turns green by itself when it is done", font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 8))
        self.steps = [ttk.Label(tab, text="○ " + s, wraplength=620, justify="left", foreground=GRAY) for s in USB_STEPS]
        for lbl in self.steps:
            lbl.pack(anchor="w", pady=3)
        self.usb_big = tk.Label(tab, text="Waiting for a phone... (checks every 3 seconds)", font=(FONT, 14, "bold"),
                                fg=GRAY, wraplength=620, justify="left", bg="#f4f6f9")
        self.usb_big.pack(anchor="w", pady=20, fill="x")

    def on_devices(self, devices: list[Device]) -> None:
        usb = [d for d in devices if d.conn == "USB"]
        states = {d.state for d in usb}
        seen, ready = bool(usb), "device" in states
        for lbl, ok, text in zip(self.steps, (seen, seen, seen, ready), USB_STEPS):
            lbl.config(text=("✔ " if ok else "○ ") + text, foreground=GREEN if ok else GRAY)
        if ready:
            self.usb_big.config(text="Phone found ✔", fg=GREEN, font=(FONT, 16, "bold"))
        elif "unauthorized" in states:
            self.usb_big.config(text="Tap Allow on the phone screen", fg=RED, font=(FONT, 22, "bold"))
        elif "offline" in states:
            self.usb_big.config(text="Phone is offline - unplug and replug the cable, then press Fix problems", fg=RED, font=(FONT, 13, "bold"))
        elif usb:
            self.usb_big.config(text=usb[0].reason, fg=RED, font=(FONT, 13, "bold"))
        else:
            self.usb_big.config(text="Waiting for a phone... (checks every 3 seconds)", fg=GRAY, font=(FONT, 14, "bold"))

    # ---------- QR ----------
    def _qr_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=14)
        self.qr_tab = tab
        self.nb.add(tab, text="QR code (Android 11+)")
        ttk.Label(tab, wraplength=620, justify="left",
                  text="On the phone: Settings > Developer options > Wireless debugging > \"Pair device with QR code\", "
                       "then scan the QR below. The PC and phone must be on the same Wi-Fi.").pack(anchor="w")
        ttk.Button(tab, text="Create QR (Start)", style="Big.TButton", command=self._start_qr).pack(pady=10)
        self.qr_label = ttk.Label(tab)
        self.qr_label.pack()
        self.qr_status = ttk.Label(tab, text="", wraplength=620, justify="left", font=(FONT, 11, "bold"))
        self.qr_status.pack(anchor="w", pady=8)
        self.qr_fallback = ttk.Button(tab, text="Use the pairing code method (method 3)", command=self._go_code)

    def _go_code(self) -> None:
        self.nb.select(self.code_tab)

    def _start_qr(self) -> None:
        try:
            from PIL import ImageTk

            image = self.app.pairing.start()
            self.photo = ImageTk.PhotoImage(image.resize((260, 260)))
        except Exception as exc:
            self.qr_status.config(text=f"Could not create the QR: {exc}", foreground=RED)
            return
        self.qr_label.config(image=self.photo)
        self.qr_fallback.pack_forget()
        self.qr_status.config(text="Waiting for the QR scan... (60 seconds)", foreground=GRAY)

    def on_pair_event(self, kind: str, text: str) -> None:
        if self.qr_tab is None:
            return
        color = {"status": GRAY, "ok": GREEN}.get(kind, RED)
        self.qr_status.config(text=text, foreground=color)
        if kind in ("fail", "timeout"):
            self.qr_fallback.pack(pady=4)
        if kind == "ok":
            self.photo = None
            self.qr_label.config(image="")
            self.app.devman.refresh_now()

    # ---------- manual code ----------
    def _code_tab(self) -> None:
        tab = ttk.Frame(self.nb, padding=14)
        self.code_tab = tab
        self.nb.add(tab, text="Pairing code")
        ttk.Label(tab, wraplength=620, justify="left",
                  text="On the phone, tap Wireless debugging > \"Pair device with pairing code\". Enter the IP:PORT and the 6-digit code it shows."
                  ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.pair_addr, self.pair_code, self.conn_addr = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(tab, text="Pair IP:PORT").grid(row=1, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.pair_addr, width=24).grid(row=1, column=1, padx=6, pady=4)
        ttk.Label(tab, text="6-digit code").grid(row=2, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.pair_code, width=12, show="*").grid(row=2, column=1, sticky="w", padx=6, pady=4)
        ttk.Button(tab, text="Pair", command=self._pair).grid(row=2, column=2, padx=6)
        ttk.Label(tab, text="Connect IP:PORT").grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Entry(tab, textvariable=self.conn_addr, width=24).grid(row=3, column=1, padx=6, pady=(14, 0))
        ttk.Button(tab, text="Connect", command=self._connect).grid(row=3, column=2, padx=6, pady=(14, 0))
        self.code_msg = ttk.Label(tab, text="", wraplength=620, justify="left", font=(FONT, 10, "bold"))
        self.code_msg.grid(row=4, column=0, columnspan=3, sticky="w", pady=14)

    def _pair(self) -> None:
        addr, code = self.pair_addr.get().strip(), self.pair_code.get().strip()
        self.pair_code.set("")          # never keep the code around
        if not addr or not code:
            self.code_msg.config(text="Enter both the IP:PORT and the code.", foreground=RED)
            return
        self.code_msg.config(text="Pairing...", foreground=GRAY)
        self.app.bg(lambda: self.app.adb.pair(addr, code), self._pair_done)

    def _pair_done(self, res: Any) -> None:
        ok = "Successfully paired" in res.text
        self.code_msg.config(text=("Pairing successful. Now enter the Connect IP:PORT and press Connect." if ok else f"Pairing failed: {res.text}"),
                             foreground=GREEN if ok else RED)

    def _connect(self) -> None:
        addr = self.conn_addr.get().strip()
        if not addr:
            self.code_msg.config(text="Enter the Connect IP:PORT.", foreground=RED)
            return
        self.code_msg.config(text="Connecting...", foreground=GRAY)
        self.app.bg(lambda: self.app.adb.connect(addr), self._connect_done)

    def _connect_done(self, res: Any) -> None:
        ok = self.app.adb.is_connected(res)
        self.code_msg.config(text=("Connected ✔" if ok else f"Connect failed: {res.text}"), foreground=GREEN if ok else RED)
        self.app.devman.refresh_now()

    def close(self) -> None:
        self.app.pairing.stop()
        self.app.wizard = None
        self.win.destroy()
