"""BANG BANG ADB window: one unified screen (sidebar + pages). Simple and Advanced are merged."""
from __future__ import annotations

import csv
import logging
import math
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Optional

import installer as installer_mod
import widgets as W
from adb_client import AdbClient
from connection import ConnectionPage
from devices import Device, DeviceManager
from help_text import brand_key
from help_window import show_brand_help
from i18n import T, set_lang
from installer import ApkGroup, ApkInfo, ApkReader, Installer, JobOptions, JobResult, fmt_version
from pairing import PairingService
from settings import Settings, app_dir
from widgets import FONT, P, Bar, Btn, DropZone, Scroll, Seg, Toast, Toggle, alive, card, lerp, tween

try:                                   # optional: drag and drop
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:                      # not installed or failed to load
    DND_FILES, TkinterDnD = None, None

try:                                   # Windows only
    import winsound
except ImportError:
    winsound = None

STATUS = {
    "waiting": ("Waiting", "mute"),
    "checking": ("Checking", "acc"),
    "installing": ("Installing", "acc"),
    "success": ("Success", "ok"),
    "failed": ("Failed", "bad"),
    "skipped": ("Skipped", "mute"),
    "sig": ("Signature mismatch", "bad"),
    "older": ("APK older (Skipped)", "warn"),
}
NAV = (("install", "📲", "Install"), ("apps", "🧩", "Apps"), ("connection", "📡", "Connection"),
       ("log", "🧾", "Log"), ("settings", "⚙", "Settings"))
BOOLS = ("animations", "sound", "wake_screen", "stay_awake", "skip_verifier", "retry_once", "open_after",
         "confirm_uninstall", "auto_csv", "front_when_done", "log_popup", "reconnect_saved", "remember_dir")
SPIN = "◐◓◑◒"
UNKNOWN, ERROR = "?", "err"


class LogPopup:
    """Small floating log window that opens when an install starts."""

    def __init__(self, app: "App") -> None:
        self.app = app
        win = self.win = tk.Toplevel(app.root)
        win.title(T("Install log"))
        win.configure(bg="#0c131b")
        win.transient(app.root)
        w, h = 440, 250
        x = app.root.winfo_rootx() + app.root.winfo_width() - w - 24
        y = app.root.winfo_rooty() + app.root.winfo_height() - h - 24
        win.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        head = tk.Frame(win, bg="#121d2a")
        head.pack(fill="x")
        self.dot = tk.Label(head, text="●", fg="#22d3a6", bg="#121d2a", font=(FONT, 10))
        self.dot.pack(side="left", padx=(12, 4), pady=8)
        self.title = tk.Label(head, text=T("Installing..."), fg="#e6edf6", bg="#121d2a", font=(FONT, 10, "bold"))
        self.title.pack(side="left")
        for text, cmd in (("✕", self.close), (T("Copy"), self.copy), (T("Full log"), self.full)):
            b = tk.Label(head, text=text, fg="#9fb0c6", bg="#121d2a", font=(FONT, 9), padx=8, cursor="hand2")
            b.pack(side="right", padx=2)
            b.bind("<Button-1>", lambda _e, c=cmd: c())
            b.bind("<Enter>", lambda _e, bb=b: bb.configure(fg="#ffffff"))
            b.bind("<Leave>", lambda _e, bb=b: bb.configure(fg="#9fb0c6"))
        self.text = tk.Text(win, bg="#0c131b", fg="#9fb0c6", font=("Consolas", 9), relief="flat", wrap="word",
                            state="disabled", padx=10, pady=8, highlightthickness=0)
        self.text.pack(fill="both", expand=True)
        for tag, color in (("cmd", "#9aa5b1"), ("ok", "#5fd38d"), ("bad", "#ff7b70")):
            self.text.tag_configure(tag, foreground=color)
        self.live, self.k = True, 0
        win.protocol("WM_DELETE_WINDOW", self.close)
        try:
            win.attributes("-alpha", 0.0)
            tween(win, 8, 25, lambda t: win.attributes("-alpha", 0.97 * t))
        except tk.TclError:
            pass
        self._pulse()

    def _pulse(self) -> None:
        if not alive(self.win):
            return
        self.k += 1
        if self.live:
            self.dot.configure(fg=lerp("#22d3a6", "#0c131b", 0.6 * (math.sin(self.k / 3) + 1) / 2))
        self.win.after(120, self._pulse)

    def reset(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self.live = True
        self.title.config(text=T("Installing..."))
        self.win.lift()

    def add(self, text: str, tag: str = "") -> None:
        self.text.config(state="normal")
        self.text.insert("end", text + "\n", tag)
        self.text.see("end")
        self.text.config(state="disabled")

    def finish(self, text: str, ok: bool) -> None:
        self.live = False
        self.dot.configure(fg="#5fd38d" if ok else "#ff7b70")
        self.title.config(text=text)

    def copy(self) -> None:
        self.app._clip(self.text.get("1.0", "end"))
        self.app.toast.show(T("Copied"))

    def full(self) -> None:
        self.app.show_page("log")
        self.app.root.lift()

    def close(self) -> None:
        self.app.popup = None
        if alive(self.win):
            self.win.destroy()


class App:
    def __init__(self) -> None:
        self.settings = Settings()
        set_lang(self.settings.get("lang"))
        W.set_theme(self.settings.get("theme"))
        W.set_anim(self.settings.get("animations"))
        self.events: queue.Queue = queue.Queue()
        self.dnd = False
        self.root = self._make_root()
        self.root.title("BANG BANG ADB")
        self.root.geometry(self.settings.get("geometry"))
        self.root.minsize(960, 660)

        # state
        self.devices: list[Device] = []
        self.checked: set[str] = set()
        self.seen: set[str] = set()
        self.handled: set[str] = set()
        self.apks: list[ApkInfo] = []
        self.groups: list[ApkGroup] = []
        self.split_choice: dict[str, bool] = {}
        self.installed: dict[str, Any] = {}
        self.checking: set[str] = set()
        self.plan_gen = 0
        self.status: dict[str, tuple[str, str]] = {}
        self.raw_errors: dict[str, str] = {}
        self.pkg_of: dict[str, str] = {}
        self.history: list[JobResult] = []
        self.batches: dict[int, dict[str, Any]] = {}
        self.batch_id = 0
        self.manual_batch: Optional[int] = None
        self.help_shown = False
        self.detail_key = ""
        self.last_rows: Optional[list] = None
        self.all_pkgs: list[str] = []
        self.adb_ok = False
        self.page = "install"
        self.popup: Optional[LogPopup] = None
        self.log_buffer: list[tuple[str, str]] = []
        self.spin_labels: dict[str, tk.Label] = {}
        self.spin_i = 0
        self.conn_page: Optional[ConnectionPage] = None
        self.toast = Toast(self.root)
        self.status_text, self.status_kind = T("Choose an APK, tick the phones, then press Install."), "info"
        self.opts_open = False

        # tk variables (they survive a UI rebuild)
        self.filter = tk.StringVar(value="all")
        self.var_grant = tk.BooleanVar(value=self.settings.get("grant"))
        self.var_force = tk.BooleanVar(value=self.settings.get("force"))
        self.var_auto = tk.BooleanVar(value=False)
        self.var_workers = tk.IntVar(value=min(10, max(1, self.settings.get("workers"))))
        self.var_timeout = tk.IntVar(value=self.settings.get("timeout"))
        self.var_cmd = tk.StringVar()
        self.var_search = tk.StringVar()
        self.var_app_phone = tk.StringVar()
        self.var_app_scope = tk.StringVar(value="user")
        self.var_setup = tk.StringVar()
        self.var_lang = tk.StringVar(value=self.settings.get("lang"))
        self.var_theme = tk.StringVar(value=self.settings.get("theme"))
        self.opt = {k: tk.BooleanVar(value=self.settings.get(k)) for k in BOOLS}
        self.app_phone_map: dict[str, Device] = {}
        self.apps_dev: Optional[Device] = None
        self.apps_scope = "user"
        installer_mod.INSTALL_TIMEOUT = self._timeout()

        # services
        self.adb = AdbClient(None, lambda msg, tag: self.events.put(("log", msg, tag)))
        self.reader = ApkReader()
        self.devman = DeviceManager(self.adb, self.settings, self.events)
        self.installer = Installer(self.adb, self.events)
        self.pairing = PairingService(self.adb, self.events)

        if self.dnd:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        self._build_all()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain)
        self.root.after(50, self._boot)
        self.root.after(150, self._spin_tick)

    def run(self) -> None:
        self.root.mainloop()

    def _make_root(self) -> tk.Tk:
        if TkinterDnD is not None:
            try:
                root = TkinterDnD.Tk()
                self.dnd = True
                return root
            except Exception:
                self.dnd = False
        return tk.Tk()

    def _timeout(self) -> int:
        try:
            return max(30, min(900, int(self.var_timeout.get())))
        except (tk.TclError, ValueError):
            return 120

    def beep(self, kind: str = "ok") -> None:
        if winsound is None or not self.opt["sound"].get():
            return
        try:
            if kind == "auto":
                winsound.Beep(1000, 150)
            else:
                winsound.MessageBeep(winsound.MB_OK if kind == "ok" else winsound.MB_ICONHAND)
        except Exception:
            pass

    # ================================================================ build everything
    def _build_all(self) -> None:
        if self.popup:
            self.popup.close()
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=P["bg"])
        W.style_ttk(self.root)
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._build_side()
        self.content = tk.Frame(self.root, bg=P["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.toast = Toast(self.root)
        self._build_setup()
        self.pages = {"install": self._page_install(self.content), "apps": self._page_apps(self.content),
                      "connection": self._page_connection(self.content), "log": self._page_log(self.content),
                      "settings": self._page_settings(self.content)}
        self._after_rebuild()

    def _after_rebuild(self) -> None:
        self.last_rows = None
        self._apks_view()
        self._render_table()
        self._update_preview()
        self._update_result_bar()
        self._update_side()
        self.set_status(self.status_text, self.status_kind)
        self.log_text.config(state="normal")
        for text, tag in self.log_buffer:
            self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        if self.conn_page:
            self.conn_page.on_devices(self.devices)
        self.refresh_app_phones()
        self.show_page(self.page)

    def _head(self, parent: tk.Misc, title: str, row: int = 0) -> tk.Frame:
        h = tk.Frame(parent, bg=P["bg"])
        h.grid(row=row, column=0, sticky="ew", padx=24, pady=(18, 10))
        tk.Label(h, text=title, font=(FONT, 18, "bold"), bg=P["bg"], fg=P["ink"]).pack(side="left")
        return h

    def _page(self, parent: tk.Misc) -> tk.Frame:
        f = tk.Frame(parent, bg=P["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        return f

    # ---------------------------------------------------------------- sidebar
    def _build_side(self) -> None:
        s = tk.Frame(self.root, bg=P["side"], width=212)
        s.grid(row=0, column=0, sticky="nsw")
        s.grid_propagate(False)
        logo = tk.Frame(s, bg=P["side"])
        logo.pack(fill="x", padx=14, pady=(20, 22))
        self.logo_ic = tk.Label(logo, text="⚡", font=(FONT, 14, "bold"), bg=P["acc"], fg="#ffffff", padx=8, pady=2)
        self.logo_ic.pack(side="left")
        tk.Label(logo, text="BANG BANG ADB", font=(FONT, 12, "bold"), bg=P["side"], fg="#ffffff").pack(side="left", padx=10)
        self.nav: dict[str, tuple[tk.Frame, tk.Frame, tk.Label]] = {}
        for key, icon, label in NAV:
            row = tk.Frame(s, bg=P["side"])
            row.pack(fill="x", padx=(0, 12), pady=1)
            bar = tk.Frame(row, width=4, bg=P["side"])
            bar.pack(side="left", fill="y")
            lb = tk.Label(row, text=f"  {icon}   {T(label)}", anchor="w", font=(FONT, 11, "bold"), bg=P["side"],
                          fg=P["side_t"], padx=10, pady=10, cursor="hand2")
            lb.pack(side="left", fill="x", expand=True, padx=(6, 0))
            for w in (row, lb):
                w.bind("<Button-1>", lambda _e, k=key: self.show_page(k))
            lb.bind("<Enter>", lambda _e, k=key: self._nav_hover(k, True))
            lb.bind("<Leave>", lambda _e, k=key: self._nav_hover(k, False))
            self.nav[key] = (row, bar, lb)
        tk.Frame(s, bg=P["side"]).pack(fill="both", expand=True)
        theme = tk.Label(s, text="🌓  " + T("Theme"), anchor="w", font=(FONT, 10), bg=P["side"], fg=P["side_t"],
                         padx=18, pady=6, cursor="hand2")
        theme.pack(fill="x")
        theme.bind("<Button-1>", lambda _e: self.set_theme("light" if self.var_theme.get() == "dark" else "dark"))
        foot = tk.Frame(s, bg=P["side"])
        foot.pack(fill="x", padx=18, pady=(2, 18))
        self.side_dot = tk.Label(foot, text="●", font=(FONT, 10), bg=P["side"], fg=P["ok"])
        self.side_dot.pack(side="left")
        self.side_info = tk.Label(foot, text="", font=(FONT, 9), bg=P["side"], fg=P["side_t"])
        self.side_info.pack(side="left", padx=6)
        self._pulse_side()

    def _nav_hover(self, key: str, on: bool) -> None:
        if key == self.page:
            return
        row, bar, lb = self.nav[key]
        col = lerp(P["side"], P["side_on"], 0.6) if on else P["side"]
        for w in (row, bar, lb):
            w.configure(bg=col)

    def _pulse_side(self) -> None:
        if not alive(self.side_dot):
            return
        n = sum(1 for d in self.devices if d.usable)
        k = (math.sin(time.time() * 3) + 1) / 2
        base = P["ok"] if (self.adb_ok and n) else (P["warn"] if self.adb_ok else P["bad"])
        self.side_dot.configure(fg=lerp(base, P["side"], 0.6 * k if n else 0))
        self.side_dot.after(120, self._pulse_side)

    def _update_side(self) -> None:
        if not alive(self.side_info):
            return
        n = sum(1 for d in self.devices if d.usable)
        self.side_info.config(text=T("ADB ready · {n} phones", n=n) if self.adb_ok else T("ADB not found"))

    def show_page(self, name: str) -> None:
        self.page = name
        target = "setup" if (not self.adb_ok and name != "settings") else name
        (self.setup_frame if target == "setup" else self.pages[name]).tkraise()
        for key, (row, bar, lb) in self.nav.items():
            on = key == name
            row.configure(bg=P["side_on"] if on else P["side"])
            lb.configure(bg=P["side_on"] if on else P["side"], fg="#ffffff" if on else P["side_t"])
            bar.configure(bg=P["acc"] if on else P["side"])
        if name == "log":
            self.log_text.see("end")

    # ---------------------------------------------------------------- ADB setup screen
    def _build_setup(self) -> None:
        f = self.setup_frame = tk.Frame(self.content, bg=P["bg"], padx=34, pady=30)
        f.grid(row=0, column=0, sticky="nsew")
        tk.Label(f, text=T("ADB not found"), font=(FONT, 20, "bold"), bg=P["bg"], fg=P["ink"]).pack(anchor="w")
        tk.Label(f, wraplength=700, justify="left", font=(FONT, 11), bg=P["bg"], fg=P["ink"],
                 text=T("Google's platform-tools (adb) is needed to install apps on phones. Press the button below to download it "
                        "automatically (internet needed). Or, if you already have adb.exe, choose it.")).pack(anchor="w", pady=14)
        self.btn_dl = Btn(f, T("Download ADB automatically"), self._download_adb, "primary", size=12, pady=10)
        self.btn_dl.pack(anchor="w", pady=4)
        Btn(f, T("Browse adb.exe"), self._browse_adb).pack(anchor="w", pady=6)
        self.dl_bar = Bar(f, height=10)
        self.dl_bar.pack(anchor="w", fill="x", pady=12)
        tk.Label(f, textvariable=self.var_setup, wraplength=700, justify="left", font=(FONT, 10, "bold"),
                 bg=P["bg"], fg=P["acc"]).pack(anchor="w")

    def _boot(self) -> None:
        path = AdbClient.find_adb(self.settings.get("adb_path"))
        if path and self._verify(path):
            self._enter_main(path)
        else:
            self.adb_ok = False
            self.show_page(self.page)

    def _verify(self, path: str) -> bool:
        old, self.adb.path = self.adb.path, path
        if self.adb.version().ok:
            return True
        self.adb.path = old
        return False

    def _enter_main(self, path: str) -> None:
        self.adb.path = path
        self.settings.set("adb_path", path)
        self.settings.save()
        self.adb_ok = True
        self._update_side()
        self.show_page("install" if self.page == "install" else self.page)

        def startup() -> None:
            self.adb.start_server()
            self.devman.start()
            if self.opt["reconnect_saved"].get():
                self.devman.reconnect_saved()

        self.bg(startup)

    def _download_adb(self) -> None:
        self.btn_dl.set_enabled(False)
        self.var_setup.set(T("Downloading..."))
        self.bg(lambda: AdbClient.download_platform_tools(lambda got, total: self.events.put(("dl", got, total))),
                self._adb_downloaded, self._download_failed)

    def _adb_downloaded(self, path: str) -> None:
        self.btn_dl.set_enabled(True)
        if self._verify(path):
            self._enter_main(path)
        else:
            self.var_setup.set(T("Cannot run adb.exe. Choose another file with Browse adb.exe."))

    def _download_failed(self, exc: Exception) -> None:
        self.btn_dl.set_enabled(True)
        self.var_setup.set(str(exc))

    def _browse_adb(self) -> None:
        path = filedialog.askopenfilename(title=T("Choose adb.exe"), filetypes=[("adb.exe", "adb.exe"), ("All", "*.*")])
        if not path:
            return
        if self._verify(path):
            self._enter_main(path)
        else:
            self.var_setup.set(T("Could not run this file. Choose the correct adb.exe."))

    # ================================================================ INSTALL page
    @staticmethod
    def _cols(frame: tk.Frame) -> None:
        for i, (weight, minsize) in enumerate(((0, 46), (2, 200), (0, 96), (0, 150), (0, 140), (3, 230))):
            frame.columnconfigure(i, weight=weight, minsize=minsize)

    def _page_install(self, parent: tk.Misc) -> tk.Frame:
        f = self._page(parent)
        f.rowconfigure(3, weight=1)
        head = self._head(f, T("Install apps"), 0)
        Btn(head, "＋  " + T("Add phone"), lambda: self.show_page("connection"), "primary").pack(side="right")

        box = card(f)
        box.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        box.columnconfigure(0, weight=1)
        self.drop = DropZone(box, T("Drop an APK here, or click to choose one") if self.dnd else T("Click to choose an APK file"),
                             T("Ctrl+O also opens the file chooser") if self.dnd else T("Drag and drop needs the tkinterdnd2 package"),
                             self.pick_apks)
        self.drop.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.apk_box = tk.Frame(box, bg=P["panel"])
        self.apk_box.grid(row=1, column=0, sticky="ew", padx=10)

        bar = tk.Frame(f, bg=P["bg"])
        bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
        tk.Label(bar, text=T("Phones"), font=(FONT, 11, "bold"), bg=P["bg"], fg=P["ink"]).pack(side="left", padx=(0, 10))
        Seg(bar, [("all", T("All")), ("usb", T("USB only")), ("wifi", T("Wi-Fi only"))], self.filter,
            self._render_table).pack(side="left")
        Btn(bar, T("Select all"), self.select_all).pack(side="left", padx=(14, 4))
        Btn(bar, T("None"), self.select_none).pack(side="left")
        Btn(bar, "🔄  " + T("Refresh"), self.refresh_all).pack(side="right")

        lc = card(f)
        lc.grid(row=3, column=0, sticky="nsew", padx=24)
        lc.columnconfigure(0, weight=1)
        lc.rowconfigure(1, weight=1)
        hdr = tk.Frame(lc, bg=P["chip"])
        hdr.grid(row=0, column=0, sticky="ew", padx=(0, 17))
        self._cols(hdr)
        for i, text in enumerate(("", T("Phone (Model / Serial)"), T("Connection"), T("Installed version"),
                                  T("Plan"), T("Status"))):
            tk.Label(hdr, text=text, font=(FONT, 9, "bold"), bg=P["chip"], fg=P["mute"]).grid(
                row=0, column=i, sticky="w", padx=6, pady=8)
        sc = Scroll(lc)
        sc.grid(row=1, column=0, sticky="nsew")
        self.rows = sc.body

        det = tk.Frame(f, bg=P["bg"])
        det.grid(row=4, column=0, sticky="ew", padx=24)
        self.detail = tk.Label(det, text="", wraplength=780, justify="left", fg=P["bad"], bg=P["bg"], font=(FONT, 10))
        self.detail.pack(side="left", fill="x", expand=True)
        self.copy_btn = Btn(det, T("Copy error"), self.copy_error, pady=3)

        run = tk.Frame(f, bg=P["bg"])
        run.grid(row=5, column=0, sticky="ew", padx=24, pady=10)
        run.columnconfigure(2, weight=1)
        self.install_btn = Btn(run, T("Install"), self.on_install, "primary", size=15, padx=36, pady=10)
        self.install_btn.grid(row=0, column=0)
        self.cancel_btn = Btn(run, T("Cancel"), self.on_cancel, "danger")
        self.cancel_btn.grid(row=0, column=1, padx=8)
        self.cancel_btn.grid_remove()
        prog = tk.Frame(run, bg=P["bg"])
        prog.grid(row=0, column=2, sticky="ew", padx=14)
        self.pbar = Bar(prog, height=10)
        self.pbar.pack(fill="x")
        self.ptext = tk.Label(prog, text=T("{done} / {total} done", done=0, total=0), bg=P["bg"], fg=P["mute"], font=(FONT, 9))
        self.ptext.pack(anchor="w", pady=(4, 0))

        self.status_lbl = tk.Label(f, text="", font=(FONT, 12), bg=P["chip"], fg=P["acc"], anchor="w", justify="left",
                                   padx=14, pady=10, wraplength=820)
        self.status_lbl.grid(row=6, column=0, sticky="ew", padx=24)

        self.result_bar = tk.Frame(f, bg=P["bg"])
        self.result_bar.grid(row=7, column=0, sticky="ew", padx=24, pady=(8, 0))
        self.btn_retry = Btn(self.result_bar, T("Retry failed"), self.retry_failed)
        self.btn_sig = Btn(self.result_bar, T("Uninstall old and retry"), self.retry_signature)
        self.btn_down = Btn(self.result_bar, T("Try downgrade (-r -d)"), self.retry_downgrade)
        self.btn_csv = Btn(self.result_bar, T("CSV Export"), self.export_csv)
        self.result_bar.grid_remove()

        oc = card(f)
        oc.grid(row=8, column=0, sticky="ew", padx=24, pady=(10, 16))
        self.opts_head = tk.Label(oc, text="", anchor="w", font=(FONT, 10, "bold"), bg=P["panel"], fg=P["ink"],
                                  padx=14, pady=10, cursor="hand2")
        self.opts_head.pack(fill="x")
        self.opts_head.bind("<Button-1>", lambda _e: self._toggle_opts())
        self.opts_body = tk.Frame(oc, bg=P["panel"])
        r1 = tk.Frame(self.opts_body, bg=P["panel"])
        r1.pack(fill="x", padx=14, pady=4)
        for text, var, cmd in ((T("Grant all permissions (-g)"), self.var_grant, self._opts_changed),
                               (T("Force reinstall"), self.var_force, self._opts_changed),
                               (T("Auto-install on new phones"), self.var_auto, self._auto_toggled),
                               (T("Open the app after install"), self.opt["open_after"], self._opts_changed)):
            Toggle(r1, var, cmd).pack(side="left")
            tk.Label(r1, text=text, bg=P["panel"], fg=P["ink"], font=(FONT, 10)).pack(side="left", padx=(6, 18))
        r2 = tk.Frame(self.opts_body, bg=P["panel"])
        r2.pack(fill="x", padx=14, pady=4)
        tk.Label(r2, text=T("Phones at once (1-10):"), bg=P["panel"], fg=P["ink"], font=(FONT, 10)).pack(side="left")
        ttk.Spinbox(r2, from_=1, to=10, width=4, textvariable=self.var_workers, command=self._opts_changed).pack(side="left", padx=8)
        tk.Label(r2, text=T("Command preview:"), bg=P["panel"], fg=P["mute"], font=(FONT, 9)).pack(side="left", padx=(18, 6))
        ttk.Entry(r2, textvariable=self.var_cmd, state="readonly", font=("Consolas", 9)).pack(side="left", fill="x", expand=True)
        r3 = tk.Frame(self.opts_body, bg=P["panel"])
        r3.pack(fill="x", padx=14, pady=(4, 14))
        for text, cmd in ((T("Restart ADB"), self.restart_adb), (T("Fix problems"), self.fix_problems),
                          (T("CSV Export"), self.export_csv), (T("Reset auto-install list"), self.reset_handled)):
            Btn(r3, text, cmd).pack(side="left", padx=(0, 8))
        self._toggle_opts(keep=True)
        return f

    def _toggle_opts(self, keep: bool = False) -> None:
        if not keep:
            self.opts_open = not self.opts_open
        self.opts_head.config(text=("▾  " if self.opts_open else "▸  ") + T("Install options"))
        if self.opts_open:
            self.opts_body.pack(fill="x")
        else:
            self.opts_body.pack_forget()

    # ---------------------------------------------------------------- page: Apps
    def _page_apps(self, parent: tk.Misc) -> tk.Frame:
        f = self._page(parent)
        f.rowconfigure(4, weight=1)
        head = self._head(f, T("Apps on phone"), 0)
        Btn(head, T("Load apps"), self.load_apps, "primary").pack(side="right")
        Btn(head, "🔄  " + T("Refresh"), self.refresh_apps).pack(side="right", padx=8)
        r1 = tk.Frame(f, bg=P["bg"])
        r1.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))
        tk.Label(r1, text=T("Phone"), font=(FONT, 11, "bold"), bg=P["bg"], fg=P["ink"]).pack(side="left", padx=(0, 10))
        self.app_phone_cb = ttk.Combobox(r1, textvariable=self.var_app_phone, state="readonly", width=56,
                                         postcommand=self.refresh_app_phones)
        self.app_phone_cb.pack(side="left")
        self.app_phone_cb.bind("<<ComboboxSelected>>", lambda _e: self.load_apps())
        r2 = tk.Frame(f, bg=P["bg"])
        r2.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
        Seg(r2, [("user", T("User apps")), ("system", T("System apps")), ("disabled", T("Disabled")), ("all", T("All"))],
            self.var_app_scope, lambda: self.load_apps() if self.var_app_phone.get() else None).pack(side="left")
        r3 = tk.Frame(f, bg=P["bg"])
        r3.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 8))
        tk.Label(r3, text=T("Search:"), bg=P["bg"], fg=P["ink"], font=(FONT, 10)).pack(side="left")
        ttk.Entry(r3, textvariable=self.var_search, width=28).pack(side="left", padx=8)
        self.var_search.trace_add("write", lambda *_: self._filter_apps())
        Btn(r3, T("Select all"), lambda: self.apps_list.select_set(0, "end")).pack(side="left", padx=(4, 4))
        Btn(r3, T("Uninstall"), lambda: self.app_action("uninstall"), "danger").pack(side="left", padx=4)
        Btn(r3, T("Clear data"), lambda: self.app_action("clear")).pack(side="left", padx=4)
        self.apps_count = tk.Label(r3, text="", bg=P["bg"], fg=P["mute"], font=(FONT, 9))
        self.apps_count.pack(side="right")
        lc = card(f)
        lc.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 20))
        lc.rowconfigure(0, weight=1)
        lc.columnconfigure(0, weight=1)
        self.apps_list = tk.Listbox(lc, selectmode="extended", exportselection=False, font=("Consolas", 10),
                                    bg=P["panel"], fg=P["ink"], selectbackground=P["acc"], selectforeground="#ffffff",
                                    activestyle="none", relief="flat", borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(lc, orient="vertical", command=self.apps_list.yview)
        self.apps_list.config(yscrollcommand=sb.set)
        self.apps_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        sb.grid(row=0, column=1, sticky="ns")
        return f

    # ---------------------------------------------------------------- page: Connection / Log
    def _page_connection(self, parent: tk.Misc) -> tk.Frame:
        self.conn_page = ConnectionPage(self, parent)
        self.conn_page.grid(row=0, column=0, sticky="nsew")
        return self.conn_page

    def _page_log(self, parent: tk.Misc) -> tk.Frame:
        f = self._page(parent)
        f.rowconfigure(1, weight=1)
        head = self._head(f, T("Log"), 0)
        Btn(head, T("Clear log"), self.clear_log).pack(side="right")
        Btn(head, T("Copy log"), self.copy_log).pack(side="right", padx=8)
        self.log_text = tk.Text(f, bg=P["logbg"], fg=P["logfg"], font=("Consolas", 10), state="disabled", wrap="word",
                                relief="flat", padx=14, pady=12, highlightthickness=0)
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        for tag, color in (("cmd", "#9aa5b1"), ("ok", "#5fd38d"), ("bad", "#ff7b70")):
            self.log_text.tag_configure(tag, foreground=color)
        return f

    # ---------------------------------------------------------------- page: Settings
    def _row(self, group: tk.Frame, title: str, sub: str, make: Callable[[tk.Frame], tk.Misc]) -> None:
        if group.winfo_children():
            tk.Frame(group, height=1, bg=P["line"]).pack(fill="x", padx=16)
        row = tk.Frame(group, bg=P["panel"])
        row.pack(fill="x", padx=16, pady=10)
        left = tk.Frame(row, bg=P["panel"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, font=(FONT, 10, "bold"), bg=P["panel"], fg=P["ink"], anchor="w").pack(fill="x")
        if sub:
            tk.Label(left, text=sub, font=(FONT, 9), bg=P["panel"], fg=P["mute"], anchor="w", justify="left",
                     wraplength=540).pack(fill="x")
        make(row).pack(side="right", padx=(12, 0))

    def _group(self, parent: tk.Misc, title: str) -> tk.Frame:
        tk.Label(parent, text=title, font=(FONT, 11, "bold"), bg=P["bg"], fg=P["ink"], anchor="w").pack(
            fill="x", padx=24, pady=(16, 6))
        g = card(parent)
        g.pack(fill="x", padx=24)
        return g

    def _tog(self, group: tk.Frame, key: str, title: str, sub: str = "", var: Optional[tk.BooleanVar] = None,
             cmd: Optional[Callable[[], None]] = None) -> None:
        v = var if var is not None else self.opt[key]
        self._row(group, title, sub, lambda r: Toggle(r, v, cmd or self._opts_changed))

    def _page_settings(self, parent: tk.Misc) -> tk.Frame:
        f = self._page(parent)
        f.rowconfigure(1, weight=1)
        self._head(f, T("Settings"), 0)
        sc = Scroll(f, bg=P["bg"])
        sc.grid(row=1, column=0, sticky="nsew")
        b = sc.body
        g = self._group(b, T("Look and sound"))
        self._row(g, T("Theme"), T("Light or dark window"),
                  lambda r: Seg(r, [("light", T("Light")), ("dark", T("Dark"))], self.var_theme,
                                lambda: self.set_theme(self.var_theme.get())))
        self._row(g, T("Language"), T("English or Bangla. The window restarts its layout."),
                  lambda r: Seg(r, [("en", "English"), ("bn", "বাংলা")], self.var_lang,
                                lambda: self.change_lang(self.var_lang.get())))
        self._tog(g, "animations", T("Animations"), T("Turn off on a slow PC"))
        self._tog(g, "sound", T("Sound after each phone"), T("A beep when a phone or a batch is done"))
        g = self._group(b, T("Install"))
        self._tog(g, "", T("Grant all permissions"), T("Adds -g to the install command"), var=self.var_grant)
        self._tog(g, "wake_screen", T("Wake the screen first"), T("Many phones refuse installs while the screen is locked"))
        self._tog(g, "stay_awake", T("Keep the phone awake while plugged in"),
                  T("Stops the screen from sleeping during the install. Restored after the batch."))
        self._tog(g, "skip_verifier", T("Skip the Play Protect scan for adb installs"),
                  T("Removes the extra popup. Switched back on after the batch."))
        self._tog(g, "retry_once", T("Retry failed phones once"), T("Automatic second try after a batch"))
        self._tog(g, "open_after", T("Open the app after install"), T("Starts the app on the phone when the install succeeds"))
        self._row(g, T("Install timeout (seconds)"), T("Stop one stuck install after this time"),
                  lambda r: ttk.Spinbox(r, from_=30, to=900, increment=30, width=6, textvariable=self.var_timeout,
                                        command=self._opts_changed))
        self._row(g, T("Phones at once (1-10)"), "",
                  lambda r: ttk.Spinbox(r, from_=1, to=10, width=6, textvariable=self.var_workers,
                                        command=self._opts_changed))
        self._tog(g, "log_popup", T("Show a small log window while installing"))
        self._tog(g, "front_when_done", T("Bring the window forward when a batch ends"))
        self._tog(g, "auto_csv", T("Save a CSV report after every batch"), T("Saved in the reports folder next to the app"))
        g = self._group(b, T("Phones and files"))
        self._tog(g, "reconnect_saved", T("Reconnect saved Wi-Fi phones at start"))
        self._tog(g, "remember_dir", T("Remember the last APK folder"))
        self._tog(g, "confirm_uninstall", T("Ask before uninstalling apps"), T("System apps always ask"))
        g = self._group(b, "ADB")
        self._row(g, T("ADB path"), self.settings.get("adb_path") or T("not set"),
                  lambda r: Btn(r, T("Change adb.exe"), self._browse_adb))
        tk.Frame(b, height=24, bg=P["bg"]).pack()
        return f

    def set_theme(self, name: str) -> None:
        self.var_theme.set(name)
        self.settings.set("theme", name)
        self.settings.save()
        W.set_theme(name)
        self._build_all()

    def change_lang(self, code: str) -> None:
        self.settings.set("lang", code)
        self.settings.save()
        set_lang(code)
        self.status_text = T("Choose an APK, tick the phones, then press Install.") if not self.apks else self.status_text
        self._build_all()

    def _opts_changed(self) -> None:
        for k in BOOLS:
            self.settings.set(k, self.opt[k].get())
        self.settings.set("grant", self.var_grant.get())
        self.settings.set("force", self.var_force.get())
        self.settings.set("timeout", self._timeout())
        installer_mod.INSTALL_TIMEOUT = self._timeout()
        W.set_anim(self.opt["animations"].get())
        self.settings.save()
        self._render_table()
        self._update_preview()

    def _bind_keys(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.pick_apks())
        self.root.bind("<F5>", lambda _e: self.refresh_all())
        self.root.bind("<Control-Return>", lambda _e: self.on_install())

    # ================================================================ helpers
    def bg(self, fn: Callable[[], Any], done: Optional[Callable[[Any], None]] = None,
           on_error: Optional[Callable[[Exception], None]] = None) -> None:
        """Run fn in a worker thread; its result comes back to the UI thread through the queue."""
        def work() -> None:
            try:
                result: Any = fn()
            except Exception as exc:
                result = exc
            if done is not None or isinstance(result, Exception):
                self.events.put(("cb", done, on_error, result))

        threading.Thread(target=work, daemon=True).start()

    def set_status(self, text: str, kind: str = "info") -> None:
        self.status_text, self.status_kind = text, kind
        lbl = getattr(self, "status_lbl", None)
        if not alive(lbl):
            return
        bg, fg, size, weight = {"info": (P["chip"], P["acc"], 12, "normal"), "ok": (P["ok"], "#ffffff", 13, "bold"),
                                "bad": (P["badbg"], P["bad"], 12, "bold")}[kind]
        start = lbl.cget("bg")
        lbl.config(text=text, fg=fg, font=(FONT, size, weight))
        tween(lbl, 6, 22, lambda t: lbl.config(bg=lerp(start, bg, t)))

    def log(self, text: str, tag: str = "") -> None:
        self.log_buffer.append((text, tag))
        if len(self.log_buffer) > 2000:
            del self.log_buffer[:200]
        if alive(getattr(self, "log_text", None)):
            self.log_text.config(state="normal")
            self.log_text.insert("end", text + "\n", tag)
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 2000:
                self.log_text.delete("1.0", f"{lines - 2000}.0")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        if self.popup:
            self.popup.add(text, tag)

    def copy_log(self) -> None:
        self._clip(self.log_text.get("1.0", "end"))
        self.toast.show(T("Copied"))

    def clear_log(self) -> None:
        self.log_buffer.clear()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _clip(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_error(self) -> None:
        self._clip(self.raw_errors.get(self.detail_key, ""))
        self.toast.show(T("Copied"))

    def dev_by_key(self, key: str) -> Optional[Device]:
        return next((d for d in self.devices if d.key == key), None)

    def ticked(self) -> list[Device]:
        return [d for d in self.devices if d.key in self.checked and d.usable]

    def _spin_tick(self) -> None:
        self.spin_i += 1
        for key, lbl in list(self.spin_labels.items()):
            if alive(lbl):
                lbl.config(text=SPIN[self.spin_i % 4])
            else:
                self.spin_labels.pop(key, None)
        self.root.after(140, self._spin_tick)

    # ================================================================ event loop
    def _drain(self) -> None:
        try:
            for _ in range(300):
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _handle(self, ev: tuple) -> None:
        kind = ev[0]
        try:
            if kind == "log":
                self.log(ev[1], ev[2])
            elif kind == "cb":
                _k, done, on_error, result = ev
                if isinstance(result, Exception):
                    (on_error or self._show_error)(result)
                elif done is not None:
                    done(result)
            elif kind == "devices":
                self._on_devices(ev[1])
            elif kind == "adb_error":
                self.set_status(ev[1], "bad")
            elif kind == "inst":
                self._on_inst(ev[1], ev[2], ev[3])
            elif kind == "row_state":
                self._on_row_state(ev[2], ev[3], ev[4])
            elif kind == "row":
                self._on_row(ev[1], ev[2])
            elif kind == "progress":
                self._on_progress(ev[1], ev[2], ev[3])
            elif kind == "batch_done":
                self._on_batch_done(ev[1])
            elif kind == "pair":
                if self.conn_page:
                    self.conn_page.on_pair_event(ev[1], ev[2])
            elif kind == "dl":
                got, total = ev[1], ev[2]
                if alive(self.dl_bar):
                    self.dl_bar.set((got * 100 / total) if total else 0, True)
                self.var_setup.set(T("Downloading: {got:.1f} / {total:.1f} MB", got=got / 1048576, total=total / 1048576)
                                   if total else T("Downloading: {got:.1f} MB", got=got / 1048576))
        except Exception as exc:     # a UI handler must never kill the loop
            logging.exception("event %s failed", kind)
            self.log(f"UI error ({kind}): {exc}", "bad")

    def _show_error(self, exc: Exception) -> None:
        self.set_status(T("Error: {err}", err=exc), "bad")
        self.log(f"Error: {exc}", "bad")

    # ================================================================ devices
    def _on_devices(self, devs: list[Device]) -> None:
        self.devices = devs
        keys = {d.key for d in devs}
        for d in devs:
            if d.usable and d.key not in self.seen:
                self.seen.add(d.key)
                self.checked.add(d.key)       # new phones start ticked
        self.checked &= keys
        self._render_table()
        self._ensure_plans()
        self._update_preview()
        self._update_side()
        self.refresh_app_phones()
        if self.conn_page:
            self.conn_page.on_devices(devs)
        if self.var_auto.get():
            new = [d for d in devs if d.usable and d.key not in self.handled]
            if new and not self.groups:
                self.set_status(T("Auto-install is on. Choose an APK first."), "bad")
            else:
                for d in new:
                    self.start_batch([d], "normal", auto=True)

    def _inst_text(self, d: Device) -> str:
        if not d.usable:
            return "—"
        val = self.installed.get(d.key, UNKNOWN)
        if val == UNKNOWN:
            return "…" if self.groups else "—"
        if val == ERROR:
            return "?"
        return T("Not installed") if val is None else fmt_version(val)

    def _plan_action(self, d: Device) -> tuple[str, str]:
        if not d.usable or not self.groups:
            return "", "—"
        val = self.installed.get(d.key, UNKNOWN)
        if val == UNKNOWN:
            return "", "…"
        if val == ERROR:
            return "", "?"
        action, label = Installer.plan(self.groups[0], val, self.var_force.get())
        extra = len(self.groups) - 1
        return action, T(label) + (f" (+{extra})" if extra > 0 else "")

    def _render_table(self) -> None:
        if not alive(getattr(self, "rows", None)):
            return
        flt = self.filter.get()
        data = []
        for d in self.devices:
            if (flt == "usb" and d.conn != "USB") or (flt == "wifi" and d.conn != "Wi-Fi"):
                continue
            code, detail = self.status.get(d.key, ("", ""))
            if not d.usable:
                text, tag = d.reason, "warn"
            elif code:
                label, tag = STATUS[code]
                text = T(label) + ((" — " + (detail[:80] + "…" if len(detail) > 80 else detail)) if detail else "")
            else:
                text, tag = "", "mute"
            chk = "☑" if d.key in self.checked else ("☐" if d.usable else "✕")
            conn = d.conn + (" (+Wi-Fi)" if d.alts and d.conn == "USB" else "")
            busy = code in ("checking", "installing")
            data.append((d.key, chk, conn, d.model or d.serial, d.serial, self._inst_text(d), self._plan_action(d)[1],
                         text, tag, busy))
        if data == self.last_rows:
            return
        self.last_rows = data
        top = self.rows.master.yview()[0] if hasattr(self.rows.master, "yview") else 0.0
        for w in self.rows.winfo_children():
            w.destroy()
        self.spin_labels = {}
        if not data:
            box = tk.Frame(self.rows, bg=P["panel"])
            box.pack(fill="x", pady=30)
            tk.Label(box, text="📱", font=(FONT, 26), bg=P["panel"]).pack()
            tk.Label(box, text=T("No phone yet. Add one to start."), font=(FONT, 11), bg=P["panel"], fg=P["mute"]).pack(pady=6)
            Btn(box, "＋  " + T("Add phone"), lambda: self.show_page("connection"), "primary").pack()
            return
        for n, (key, chk, conn, model, serial, inst, plan, text, tag, busy) in enumerate(data):
            if n:
                tk.Frame(self.rows, height=1, bg=P["line"]).pack(fill="x")
            row = tk.Frame(self.rows, bg=P["panel"], cursor="hand2")
            row.pack(fill="x")
            self._cols(row)
            on = chk == "☑"
            tk.Label(row, text=chk, font=(FONT, 16), bg=P["panel"], fg=P["acc"] if on else P["mute"]).grid(
                row=0, column=0, padx=6, pady=10)
            name = tk.Frame(row, bg=P["panel"])
            name.grid(row=0, column=1, sticky="w", padx=6)
            tk.Label(name, text=model, font=(FONT, 10, "bold"), bg=P["panel"], fg=P["ink"], anchor="w").pack(anchor="w")
            tk.Label(name, text=serial, font=(FONT, 8), bg=P["panel"], fg=P["mute"], anchor="w").pack(anchor="w")
            tk.Label(row, text=conn, font=(FONT, 8, "bold"), bg=P["chip"], fg=P["acc"], padx=6).grid(row=0, column=2, sticky="w", padx=6)
            tk.Label(row, text=inst, font=(FONT, 10), bg=P["panel"], fg=P["ink"], anchor="w").grid(row=0, column=3, sticky="w", padx=6)
            tk.Label(row, text=plan, font=(FONT, 10), bg=P["panel"], fg=P["ink"], anchor="w").grid(row=0, column=4, sticky="w", padx=6)
            st = tk.Frame(row, bg=P["panel"])
            st.grid(row=0, column=5, sticky="w", padx=6)
            if busy:
                sp = tk.Label(st, text=SPIN[self.spin_i % 4], font=(FONT, 11, "bold"), bg=P["panel"], fg=P["acc"])
                sp.pack(side="left", padx=(0, 6))
                self.spin_labels[key] = sp
            if tag == "ok" and "✔" not in text:
                text = "✔ " + text
            tk.Label(st, text=text, font=(FONT, 10, "bold"), bg=P["panel"], fg=P[tag], wraplength=300, justify="left",
                     anchor="w").pack(side="left")
            for w in [row] + list(row.winfo_children()) + list(name.winfo_children()) + list(st.winfo_children()) + [name, st]:
                w.bind("<Button-1>", lambda _e, k=key: self._row_click(k))
        try:
            self.rows.master.yview_moveto(top)
        except tk.TclError:
            pass

    def _row_click(self, key: str) -> None:
        dev = self.dev_by_key(key)
        if dev:
            if dev.usable:
                self.checked.symmetric_difference_update({key})
                self._update_preview()
            self._show_detail(key)
            self._render_table()

    def _show_detail(self, key: str) -> None:
        dev = self.dev_by_key(key)
        code, detail = self.status.get(key, ("", ""))
        self.detail_key = key
        self.detail.config(text=(detail or (dev.reason if dev and not dev.usable else "")))
        if self.raw_errors.get(key):
            self.copy_btn.pack(side="right")
        else:
            self.copy_btn.pack_forget()

    def select_all(self) -> None:
        self.checked |= {d.key for d in self.devices if d.usable}
        self._render_table()
        self._update_preview()

    def select_none(self) -> None:
        self.checked.clear()
        self._render_table()
        self._update_preview()

    def refresh_all(self) -> None:
        self.installed.clear()
        self.checking.clear()
        self.plan_gen += 1
        self.devman.refresh_now()
        self.toast.show(T("Refreshing phones..."))

    def _ensure_plans(self) -> None:
        if not self.groups:
            return
        need = [d for d in self.devices if d.usable and d.key not in self.installed and d.key not in self.checking]
        if need:
            self.checking.update(d.key for d in need)
            self.installer.check_plans(self.plan_gen, need, self.groups[0])

    def _on_inst(self, gen: int, key: str, value: Any) -> None:
        if gen != self.plan_gen:
            return
        self.checking.discard(key)
        self.installed[key] = value
        self._render_table()
        self._update_preview()

    def _update_preview(self) -> None:
        dev = next(iter(self.ticked()), None)
        serial = dev.serial if dev else "SERIAL"
        paths = self.groups[0].paths if self.groups else [r"C:\path\app.apk"]
        action = self._plan_action(dev)[0] if dev else ""
        replace = action in ("update", "reinstall", "")
        self.var_cmd.set(self.adb.preview(serial, paths, self.var_grant.get(), replace, False))

    # ================================================================ APKs
    def pick_apks(self) -> None:
        start = (self.settings.get("last_apk_dir") if self.opt["remember_dir"].get() else "") or None
        paths = filedialog.askopenfilenames(title=T("Choose APK"), initialdir=start,
                                            filetypes=[("APK", "*.apk"), ("All files", "*.*")])
        if paths:
            self.add_apks(list(paths))

    def _on_drop(self, event: Any) -> None:
        self.add_apks(list(self.root.tk.splitlist(event.data)))

    def add_apks(self, paths: list[str]) -> None:
        if not self.adb_ok:
            return
        bundles = [Path(p).name for p in paths if Path(p).suffix.lower() in (".apks", ".xapk", ".aab")]
        if bundles:
            messagebox.showinfo(T("This format cannot be installed directly"),
                                T("These files cannot be installed directly:") + "\n" + "\n".join(bundles) + "\n\n" +
                                T("First extract them like a ZIP and give the .apk files inside."))
        have = {a.path for a in self.apks}
        good = [p for p in paths if Path(p).suffix.lower() == ".apk" and p not in have]
        if not good:
            return
        if self.opt["remember_dir"].get():
            self.settings.set("last_apk_dir", str(Path(good[0]).parent))
        self.set_status(T("Reading APK..."))
        self.bg(lambda: [self.reader.read(p) for p in good], self._apks_read)

    def _apks_read(self, infos: list[ApkInfo]) -> None:
        self.apks.extend(infos)
        unreadable = [i.name for i in infos if not i.package]
        by_pkg: dict[str, list[ApkInfo]] = {}
        for a in self.apks:
            if a.package:
                by_pkg.setdefault(a.package, []).append(a)
        for pkg, lst in by_pkg.items():
            if len(lst) > 1 and pkg not in self.split_choice:
                self.split_choice[pkg] = messagebox.askyesno(
                    T("Split APK?"), T("{pkg} has {n} files.\nAre these split APKs of the same app? (adb install-multiple will be used)",
                                       pkg=pkg, n=len(lst)))
        self._apks_changed()
        if unreadable:
            self.set_status(T("Could not read APK info (run pip install pyaxmlparser or keep aapt available). "
                              "The package name will be asked at install time."))

    def remove_apk(self, path: str) -> None:
        self.apks = [a for a in self.apks if a.path != path]
        self._apks_changed()

    def _build_groups(self) -> list[ApkGroup]:
        groups: list[ApkGroup] = []
        done: set[str] = set()
        for a in self.apks:
            if a.package and self.split_choice.get(a.package):
                if a.package not in done:
                    done.add(a.package)
                    groups.append(ApkGroup([x for x in self.apks if x.package == a.package], True))
            else:
                groups.append(ApkGroup([a]))
        return groups

    def _apks_view(self) -> None:
        if not alive(getattr(self, "apk_box", None)):
            return
        for child in self.apk_box.winfo_children():
            child.destroy()
        for a in self.apks:
            row = tk.Frame(self.apk_box, bg=P["panel"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text="APK", font=(FONT, 9, "bold"), bg=P["acc"], fg="#ffffff", padx=8, pady=6).pack(side="left")
            split = " [split]" if a.package and self.split_choice.get(a.package) else ""
            vc = a.version_code if a.version_code is not None else "?"
            info = tk.Frame(row, bg=P["panel"])
            info.pack(side="left", padx=10)
            tk.Label(info, text=a.name + split, font=(FONT, 10, "bold"), bg=P["panel"], fg=P["ink"]).pack(anchor="w")
            tk.Label(info, text=f"{a.package or T('unknown package')}  ·  versionName {a.version_name or '?'}  ·  versionCode {vc}",
                     font=(FONT, 9), bg=P["panel"], fg=P["mute"]).pack(anchor="w")
            Btn(row, "✕", lambda p=a.path: self.remove_apk(p), "ghost", padx=8, pady=2).pack(side="right")

    def _apks_changed(self) -> None:
        self.groups = self._build_groups()
        self._apks_view()
        self.plan_gen += 1
        self.installed.clear()
        self.checking.clear()
        self._ensure_plans()
        self._render_table()
        self._update_preview()
        self.set_status(T("APK ready. Tick the phones and press Install.") if self.apks
                        else T("Choose an APK, tick the phones, then press Install."))

    # ================================================================ install
    def _ask_missing_packages(self) -> bool:
        for apk in self.apks:
            if not apk.package:
                name = simpledialog.askstring(T("Package name"),
                                              T("Enter the package name of {name} (for example com.example.app):", name=apk.name))
                if not name or not name.strip():
                    return False
                apk.package = name.strip()
        self.groups = self._build_groups()
        return True

    def _options(self, replace: bool = False, targets: Optional[dict[str, set[str]]] = None) -> JobOptions:
        try:
            workers = max(1, min(10, int(self.var_workers.get())))
        except (tk.TclError, ValueError):
            workers = 5
        self.settings.set("workers", workers)
        installer_mod.INSTALL_TIMEOUT = self._timeout()
        return JobOptions(self.var_grant.get(), self.var_force.get(), workers, replace, targets or {})

    def on_install(self) -> None:
        if self.manual_batch is not None:
            return
        if not self.groups:
            self.set_status(T("Choose an APK first."), "bad")
            self.toast.show(T("Choose an APK first."), "bad")
            return
        devices = self.ticked()
        if not devices:
            self.set_status(T("Tick at least one phone."), "bad")
            self.toast.show(T("Tick at least one phone."), "bad")
            return
        if not self._ask_missing_packages():
            return
        self.start_batch(devices, "normal")

    def _open_popup(self) -> None:
        if self.popup and alive(self.popup.win):
            self.popup.reset()
        else:
            self.popup = LogPopup(self)

    def _shell(self, serial: str, *args: str) -> None:
        self.adb.run(["shell", *args], timeout=15, serial=serial)

    def _prep(self, devices: list[Device]) -> None:
        """Before installing: wake the phone, keep it awake, skip the Play Protect scan (all optional)."""
        for d in devices:
            try:
                if self.opt["wake_screen"].get():
                    self._shell(d.serial, "input", "keyevent", "KEYCODE_WAKEUP")
                    self._shell(d.serial, "wm", "dismiss-keyguard")
                if self.opt["stay_awake"].get():
                    self._shell(d.serial, "svc", "power", "stayon", "usb")
                if self.opt["skip_verifier"].get():
                    self._shell(d.serial, "settings", "put", "global", "verifier_verify_adb_installs", "0")
            except Exception:
                logging.exception("prep failed for %s", d.serial)

    def _restore(self, serials: list[str]) -> None:
        """After the batch: put the phone settings back."""
        for ser in serials:
            try:
                if self.opt["stay_awake"].get():
                    self._shell(ser, "svc", "power", "stayon", "false")
                if self.opt["skip_verifier"].get():
                    self._shell(ser, "settings", "put", "global", "verifier_verify_adb_installs", "1")
            except Exception:
                logging.exception("restore failed for %s", ser)

    def start_batch(self, devices: list[Device], mode: str, auto: bool = False, replace: bool = False,
                    targets: Optional[dict[str, set[str]]] = None, retry: bool = False) -> None:
        self.batch_id += 1
        bid = self.batch_id
        self.batches[bid] = {"total": len(devices), "results": [], "auto": auto, "retry": retry,
                             "serials": [d.serial for d in devices]}
        self.help_shown = False
        for d in devices:
            self.status[d.key] = ("waiting", "")
            self.handled.add(d.key)
        if not auto:
            self.manual_batch = bid
            self.install_btn.set_enabled(False)
            self.cancel_btn.grid()
            self.result_bar.grid_remove()
            self.pbar.set(0, True)
            self.ptext.config(text=T("{done} / {total} done", done=0, total=len(devices)))
            self.set_status(T("Installing... keep the phones unlocked."))
            if self.opt["log_popup"].get():
                self._open_popup()
        self._render_table()
        opts = self._options(replace, targets)

        def go(_r: Any = None) -> None:
            self.installer.start(bid, devices, self.groups, opts, mode)

        if any(self.opt[k].get() for k in ("wake_screen", "stay_awake", "skip_verifier")):
            self.bg(lambda: self._prep(devices), go)
        else:
            go()

    def on_cancel(self) -> None:
        if self.manual_batch is not None:
            if self.manual_batch in self.batches:
                self.batches[self.manual_batch]["cancelled"] = True
            self.installer.cancel(self.manual_batch)
            self.set_status(T("Cancelling... running jobs will finish first."))

    def _on_row_state(self, key: str, status: str, detail: str) -> None:
        self.status[key] = (status, detail)
        self._render_table()

    def _on_row(self, bid: int, res: JobResult) -> None:
        self.status[res.key] = (res.status, res.detail)
        if res.raw:
            self.raw_errors[res.key] = res.raw
        else:
            self.raw_errors.pop(res.key, None)
        if res.package:
            self.pkg_of[res.key] = res.package
        self.history.append(res)
        if bid in self.batches:
            self.batches[bid]["results"].append(res)
        label = STATUS[res.status][0]
        self.log(f"{res.name} ({res.serial}): {label} {res.detail}".rstrip(),
                 "ok" if res.status in ("success", "skipped") else "bad")
        if res.status == "success" and res.package and self.opt["open_after"].get():
            self.bg(lambda: self.adb.run(["shell", "monkey", "-p", res.package, "-c", "android.intent.category.LAUNCHER", "1"],
                                         timeout=15, serial=res.serial))
        if res.brand_help and not self.help_shown:
            self.help_shown = True
            show_brand_help(self, brand_key(res.manufacturer))
        self._render_table()

    def _on_progress(self, bid: int, done: int, total: int) -> None:
        if bid == self.manual_batch:
            self.pbar.set(done * 100 / max(total, 1), done < total)
            self.ptext.config(text=T("{done} / {total} done", done=done, total=total))

    def _on_batch_done(self, bid: int) -> None:
        batch = self.batches.pop(bid, None)
        if not batch:
            return
        results: list[JobResult] = batch["results"]
        if any(self.opt[k].get() for k in ("stay_awake", "skip_verifier")):
            self.bg(lambda: self._restore(batch["serials"]))
        for r in results:
            self.installed.pop(r.key, None)
        self._ensure_plans()
        if batch["auto"]:
            self._auto_done(results[0] if results else None)
            return
        failed = [d for d in self._keys_with("failed")]
        if self.opt["retry_once"].get() and failed and not batch["retry"] and not batch.get("cancelled"):
            self.set_status(T("Trying the failed phones once more..."))
            self.log(T("Auto retry: {n} phone(s)", n=len(failed)), "cmd")
            self.start_batch(failed, "normal", replace=True, retry=True)
            return
        self.manual_batch = None
        self.install_btn.set_enabled(True)
        self.cancel_btn.grid_remove()
        ok = sum(r.status == "success" for r in results)
        bad = sum(r.status in ("failed", "sig") for r in results)
        skip = sum(r.status in ("skipped", "older") for r in results)
        self.pbar.set(100, False)
        self.set_status(T("{ok} success, {bad} failed, {skip} skipped", ok=ok, bad=bad, skip=skip), "ok" if bad == 0 else "bad")
        self.toast.show(T("Batch finished"), "ok" if bad == 0 else "bad")
        self.beep("ok" if bad == 0 else "bad")
        if self.popup:
            self.popup.finish(T("Finished ✔") if bad == 0 else T("Finished with {n} problem(s)", n=bad), bad == 0)
        if self.opt["front_when_done"].get():
            self._bring_front()
        if self.opt["auto_csv"].get() and results:
            self._auto_csv(results)
        self._update_result_bar()

    def _bring_front(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(500, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _auto_done(self, res: Optional[JobResult]) -> None:
        if res and res.status in ("success", "skipped"):
            self.set_status(T("✔ Done - plug in the next phone"), "ok")
            self.beep("auto")
        elif res:
            self.set_status(f"{res.name}: {res.detail or T('Failed')}", "bad")
            self.beep("bad")

    # ---------- follow-up actions ----------
    def _keys_with(self, code: str) -> list[Device]:
        return [d for d in self.devices if d.usable and self.status.get(d.key, ("", ""))[0] == code]

    def _update_result_bar(self) -> None:
        if not alive(getattr(self, "result_bar", None)):
            return
        for btn in (self.btn_retry, self.btn_sig, self.btn_down, self.btn_csv):
            btn.pack_forget()
        shown = False
        for btn, code in ((self.btn_retry, "failed"), (self.btn_sig, "sig"), (self.btn_down, "older")):
            if self._keys_with(code):
                btn.pack(side="left", padx=(0, 8))
                shown = True
        if self.history:
            self.btn_csv.pack(side="left", padx=(0, 8))
            shown = True
        if shown:
            self.result_bar.grid()
        else:
            self.result_bar.grid_remove()

    def retry_failed(self) -> None:
        devs = self._keys_with("failed")
        if devs and self.manual_batch is None:
            self.start_batch(devs, "normal", replace=True)

    def _targets(self, devs: list[Device]) -> dict[str, set[str]]:
        return {d.key: {self.pkg_of[d.key]} for d in devs if d.key in self.pkg_of}

    def retry_signature(self) -> None:
        devs = self._keys_with("sig")
        if not devs or self.manual_batch is not None:
            return
        pkgs = sorted({self.pkg_of.get(d.key, "?") for d in devs})
        names = "\n".join(f"  • {d.model} ({d.serial})" for d in devs)
        if messagebox.askyesno(T("Confirm"), T("App: {pkgs}\nPhones:\n{names}\n\nThe old app will be uninstalled and the new one installed.\n"
                                               "Warning: all data of this app will be erased!\n\nContinue?",
                                               pkgs=", ".join(pkgs), names=names), icon="warning"):
            self.start_batch(devs, "uninstall_retry", targets=self._targets(devs))

    def retry_downgrade(self) -> None:
        devs = self._keys_with("older")
        if not devs or self.manual_batch is not None:
            return
        names = "\n".join(f"  • {d.model} ({d.serial})" for d in devs)
        if messagebox.askyesno(T("Downgrade"), T("Phones:\n{names}\n\nWill try to install the older version with -r -d.\n"
                                                 "Note: Android usually allows downgrade only for debuggable apps, so this may fail.\n"
                                                 "Then you must Uninstall and install the older version, which erases the app data.\n\nTry it?",
                                                 names=names), icon="warning"):
            self.start_batch(devs, "downgrade", targets=self._targets(devs))

    def _write_csv(self, path: str, rows: list[JobResult]) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Phone", "Connection", "Serial", "Old version", "New version", "Result", "Time"])
            for r in rows:
                w.writerow([r.name, r.conn, r.serial, r.old, r.new, f"{r.status} {r.detail}".strip(), r.when])

    def export_csv(self) -> None:
        if not self.history:
            messagebox.showinfo("CSV", T("There are no results yet."))
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="apk-install-results.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            self._write_csv(path, self.history)
            self.set_status(T("CSV saved: {path}", path=path))
        except OSError as exc:
            messagebox.showerror("CSV", T("Could not write the file: {err}", err=exc))

    def _auto_csv(self, rows: list[JobResult]) -> None:
        try:
            folder = app_dir() / "reports"
            folder.mkdir(exist_ok=True)
            path = folder / f"apk-install-{datetime.now():%Y%m%d-%H%M%S}.csv"
            self._write_csv(str(path), rows)
            self.log(T("CSV saved: {path}", path=path), "ok")
        except OSError:
            logging.exception("auto csv failed")

    # ================================================================ auto-install
    def _auto_toggled(self) -> None:
        if self.var_auto.get():
            self.handled |= {d.key for d in self.devices if d.usable}   # only NEW phones count
            self.set_status(T("Auto-install is on. From now on, every new phone you plug in will be installed."))

    def reset_handled(self) -> None:
        self.handled.clear()
        self.set_status(T("Auto-install list reset (all phones will count as new again)."))

    # ================================================================ tools
    def restart_adb(self) -> None:
        def work() -> str:
            self.adb.kill_server()
            self.adb.start_server()
            self.devman.refresh_now()
            return T("ADB restarted.")
        self.bg(work, lambda msg: (self.set_status(msg), self.toast.show(msg, "ok")))

    def fix_problems(self) -> None:
        self.set_status(T("Finding and fixing problems..."))

        def work() -> str:
            self.adb.kill_server()
            time.sleep(1)
            self.adb.start_server()
            self.devman.reconnect_saved()
            time.sleep(2)
            devs = self.devman.refresh() or []
            lines = [f"• {d.model} ({d.conn}, {d.serial}): {d.reason}" for d in devs if not d.usable]
            live = {d.serial for d in devs} | {a for d in devs for a in d.alts}
            for p in self.settings.saved_phones():
                if p.get("addr") not in live and not any(d.key == p.get("key") for d in devs):
                    lines.append(f"• {p.get('name', '?')} ({p.get('addr')}): " +
                                 T("not connected - Wireless debugging ON? Same Wi-Fi? AP isolation off on the router? "
                                   "If needed, pair again from Add phone."))
            return "\n".join(lines) or T("All phones are fine ✔")

        self.bg(work, self._fix_done)

    def _fix_done(self, report: str) -> None:
        self.set_status(T("Fix problems finished."))
        win = tk.Toplevel(self.root)
        win.title(T("Problem fix report"))
        win.geometry("640x320")
        win.configure(bg=P["bg"])
        txt = tk.Text(win, wrap="word", font=(FONT, 11), padx=12, pady=12, bg=P["panel"], fg=P["ink"], relief="flat")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", report)
        txt.config(state="disabled")

    # ================================================================ Apps tab
    def refresh_app_phones(self) -> None:
        if not alive(getattr(self, "app_phone_cb", None)):
            return
        self.app_phone_map = {f"{d.model or d.serial} · {d.conn} · {d.serial}": d for d in self.devices if d.usable}
        labels = list(self.app_phone_map)
        self.app_phone_cb["values"] = labels
        if self.var_app_phone.get() not in labels:
            ticked = self.ticked()
            pick = next((lb for lb, d in self.app_phone_map.items() if ticked and d.key == ticked[0].key),
                        labels[0] if labels else "")
            self.var_app_phone.set(pick)

    def refresh_apps(self) -> None:
        self.devman.refresh_now()
        self.refresh_app_phones()
        if self.var_app_phone.get():
            self.load_apps()
        else:
            self.toast.show(T("No phone found. Add a phone first."), "bad")

    def load_apps(self) -> None:
        self.refresh_app_phones()
        dev = self.app_phone_map.get(self.var_app_phone.get())
        if not dev:
            messagebox.showinfo(T("Apps"), T("No phone found. Add a phone first."))
            return
        scope = self.var_app_scope.get()
        self.set_status(T("{phone}: loading the app list...", phone=dev.model or dev.serial))
        self.bg(lambda: self.adb.list_packages(dev.serial, scope), lambda pkgs: self._apps_loaded(pkgs, dev, scope))

    def _apps_loaded(self, pkgs: list[str], dev: Device, scope: str) -> None:
        self.all_pkgs = pkgs
        self.apps_dev = dev
        self.apps_scope = scope
        self.set_status(T("{phone}: found {n} app(s).", phone=dev.model or dev.serial, n=len(pkgs)))
        self._filter_apps()
        self.toast.show(T("{n} apps loaded", n=len(pkgs)))

    def _filter_apps(self) -> None:
        if not alive(getattr(self, "apps_list", None)):
            return
        q = self.var_search.get().strip().lower()
        self.apps_list.delete(0, "end")
        for pkg in self.all_pkgs:
            if q in pkg.lower():
                self.apps_list.insert("end", pkg)
        self.apps_count.config(text=T("Showing {a} / total {b}", a=self.apps_list.size(), b=len(self.all_pkgs)))

    def app_action(self, kind: str) -> None:
        sel = self.apps_list.curselection()
        dev = self.apps_dev
        if not sel or dev is None:
            messagebox.showinfo(T("Apps"), T("Load the apps first, then select one or more apps."))
            return
        pkgs = [self.apps_list.get(i) for i in sel]
        system = self.apps_scope in ("system", "disabled")
        verb = T("Uninstall") if kind == "uninstall" else T("Clear data")
        shown = "\n".join(f"  • {p}" for p in pkgs[:12]) + (("\n  " + T("... and {n} more", n=len(pkgs) - 12)) if len(pkgs) > 12 else "")
        warn = T("Warning: all data of the app will be erased!")
        if system and kind == "uninstall":
            warn = T("Warning: these are system apps. Removing the wrong app can break calls, network or settings on the phone.\n"
                     "The app is removed for the current user only; a factory reset brings it back.")
        if kind == "clear" or system or self.opt["confirm_uninstall"].get():
            if not messagebox.askyesno(T("Confirm"), T("{verb} - {n} app(s)\nPhone: {phone} ({serial})\n\n{shown}\n\n{warn}\n\nContinue?",
                                                       verb=verb, n=len(pkgs), phone=dev.model or dev.serial, serial=dev.serial,
                                                       shown=shown, warn=warn), icon="warning"):
                return

        def work() -> tuple[list[str], list[str]]:
            out: list[str] = []
            done: list[str] = []
            for pkg in pkgs:
                if kind == "clear":
                    res = self.adb.clear_data(dev.serial, pkg)
                elif system:
                    res = self.adb.uninstall_user0(dev.serial, pkg)
                else:
                    res = self.adb.uninstall(dev.serial, pkg)
                ok = res.ok and "Success" in res.text
                if ok:
                    done.append(pkg)
                out.append(f"{dev.model}: {verb} {pkg} -> {'OK' if ok else 'Failed'} {res.text}")
            return out, done

        self.bg(work, lambda r: self._app_action_done(r, kind))

    def _app_action_done(self, result: tuple[list[str], list[str]], kind: str) -> None:
        lines, done = result
        for line in lines:
            self.log(line, "bad" if "Failed" in line else "ok")
        if kind == "uninstall" and done:
            gone = set(done)
            self.all_pkgs = [p for p in self.all_pkgs if p not in gone]
            self._filter_apps()
        self.installed.clear()
        self.checking.clear()
        self._ensure_plans()
        failed = len(lines) - len(done) if kind == "uninstall" else sum("Failed" in l for l in lines)
        self.set_status(T("Done. {ok} succeeded, {bad} failed. Details are in the Log tab.", ok=len(lines) - failed, bad=failed),
                        "bad" if failed else "info")

    # ================================================================ close
    def on_close(self) -> None:
        try:
            self.settings.set("geometry", self.root.geometry())
            self.settings.set("theme", self.var_theme.get())
            self.settings.set("lang", self.var_lang.get())
            self.settings.save()
        finally:
            self.devman.stop()
            self.pairing.stop()
            self.root.destroy()
