"""App: the Tkinter user interface (Simple + Advanced mode). Widgets are touched only here."""
from __future__ import annotations

import csv
import logging
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Optional

from adb_client import AdbClient
from devices import Device, DeviceManager
from help_text import brand_key
from installer import (ApkGroup, ApkInfo, ApkReader, Installer, JobOptions, JobResult, fmt_version)
from pairing import PairingService
from settings import Settings
from wizard import Wizard, build_wireless_tools, show_brand_help

try:                                   # optional: drag and drop
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:                      # not installed or failed to load
    DND_FILES, TkinterDnD = None, None

try:                                   # Windows only
    import winsound
except ImportError:
    winsound = None

FONT = "Nirmala UI"
BG = "#f4f6f9"
COLORS = {"ok": "#1b7f3b", "bad": "#c62828", "run": "#1565c0", "warn": "#b26a00", "gray": "#6b7280"}
STATUS = {
    "waiting": ("Waiting", "gray"),
    "checking": ("Checking", "run"),
    "installing": ("Installing", "run"),
    "success": ("Success", "ok"),
    "failed": ("Failed", "bad"),
    "skipped": ("Skipped", "gray"),
    "sig": ("Signature mismatch", "bad"),
    "older": ("APK older (Skipped)", "warn"),
}
UNKNOWN, ERROR = "?", "err"


def beep(kind: str = "ok") -> None:
    if winsound is None:
        return
    try:
        if kind == "auto":
            winsound.Beep(1000, 150)
        else:
            winsound.MessageBeep(winsound.MB_OK if kind == "ok" else winsound.MB_ICONHAND)
    except Exception:
        pass


class App:
    def __init__(self) -> None:
        self.settings = Settings()
        self.events: queue.Queue = queue.Queue()
        self.dnd = False
        self.root = self._make_root()
        self.root.title("BANG BANG ADB")
        self.root.geometry(self.settings.get("geometry"))
        self.root.minsize(880, 620)
        self.root.configure(bg=BG)

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
        self.last_rows: list[Any] = []
        self.all_pkgs: list[str] = []
        self.wizard: Optional[Wizard] = None

        # tk variables
        mode = self.settings.get("mode")
        self.mode = tk.StringVar(value=mode if mode in ("simple", "advanced") else "simple")
        self.filter = tk.StringVar(value="all")
        self.var_grant = tk.BooleanVar(value=self.settings.get("grant"))
        self.var_force = tk.BooleanVar(value=self.settings.get("force"))
        self.var_auto = tk.BooleanVar(value=False)
        self.var_workers = tk.IntVar(value=min(10, max(1, self.settings.get("workers"))))
        self.var_cmd = tk.StringVar()
        self.var_search = tk.StringVar()
        self.var_app_phone = tk.StringVar()
        self.var_app_scope = tk.StringVar(value="user")
        self.app_phone_map: dict[str, Device] = {}
        self.apps_dev: Optional[Device] = None
        self.apps_scope = "user"
        self.var_setup = tk.StringVar()

        # services
        self.adb = AdbClient(None, lambda msg, tag: self.events.put(("log", msg, tag)))
        self.reader = ApkReader()
        self.devman = DeviceManager(self.adb, self.settings, self.events)
        self.installer = Installer(self.adb, self.events)
        self.pairing = PairingService(self.adb, self.events)

        self._style()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_header()
        self._build_setup()
        self._build_main()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain)
        self.root.after(50, self._boot)

    def run(self) -> None:
        self.root.mainloop()

    # ================================================================ setup
    def _make_root(self) -> tk.Tk:
        if TkinterDnD is not None:
            try:
                root = TkinterDnD.Tk()
                self.dnd = True
                return root
            except Exception:
                self.dnd = False
        return tk.Tk()

    def _style(self) -> None:
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", font=(FONT, 10), background=BG)
        for name in ("TFrame", "TLabel", "TLabelframe", "TCheckbutton", "TRadiobutton"):
            st.configure(name, background=BG)
        st.configure("TLabelframe.Label", background=BG, font=(FONT, 10, "bold"))
        st.configure("Treeview", rowheight=46, font=(FONT, 10), background="white", fieldbackground="white")
        st.configure("Treeview.Heading", font=(FONT, 10, "bold"))
        st.configure("Big.TButton", font=(FONT, 12, "bold"), padding=8)
        st.configure("Go.TButton", font=(FONT, 16, "bold"), padding=(28, 12), foreground="white", background="#1565c0")
        st.map("Go.TButton", background=[("disabled", "#9db7d8"), ("active", "#0d47a1")],
               foreground=[("disabled", "white")])

    def _build_header(self) -> None:
        head = ttk.Frame(self.root, padding=(12, 10))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="BANG BANG ADB", font=(FONT, 16, "bold")).pack(side="left")
        box = ttk.Frame(head)
        box.pack(side="left", padx=20)
        for text, val in (("Simple", "simple"), ("Advanced", "advanced")):
            ttk.Radiobutton(box, text=text, value=val, variable=self.mode, style="Toolbutton",
                            command=self.apply_mode).pack(side="left", padx=2)
        ttk.Button(head, text="Help", command=lambda: show_brand_help(self, "generic")).pack(side="right", padx=4)
        self.add_btn = ttk.Button(head, text="+ Add phone", style="Big.TButton",
                                  command=self.open_wizard, state="disabled")
        self.add_btn.pack(side="right", padx=4)

    def _build_setup(self) -> None:
        f = self.setup_frame = ttk.Frame(self.root, padding=30)
        ttk.Label(f, text="ADB not found", font=(FONT, 18, "bold")).pack(anchor="w")
        ttk.Label(f, wraplength=700, justify="left", font=(FONT, 11),
                  text="Google's platform-tools (adb) is needed to install apps on phones. Press the button below to download it automatically "
                       "(internet needed). Or, if you already have adb.exe, choose it.").pack(anchor="w", pady=12)
        self.btn_dl = ttk.Button(f, text="Download ADB automatically",
                                 style="Big.TButton", command=self._download_adb)
        self.btn_dl.pack(anchor="w", pady=4)
        ttk.Button(f, text="Browse adb.exe", command=self._browse_adb).pack(anchor="w", pady=4)
        self.dl_bar = ttk.Progressbar(f, length=420, mode="determinate")
        self.dl_bar.pack(anchor="w", pady=10)
        ttk.Label(f, textvariable=self.var_setup, wraplength=700, justify="left", font=(FONT, 10, "bold")).pack(anchor="w")

    def _boot(self) -> None:
        path = AdbClient.find_adb(self.settings.get("adb_path"))
        if path and self._verify(path):
            self._enter_main(path)
        else:
            self.main.grid_remove()
            self.setup_frame.grid(row=1, column=0, sticky="nsew")

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
        self.setup_frame.grid_remove()
        self.main.grid(row=1, column=0, sticky="nsew")
        self.add_btn.state(["!disabled"])
        self.apply_mode()

        def startup() -> None:
            self.adb.start_server()
            self.devman.start()
            self.devman.reconnect_saved()

        self.bg(startup)

    def _download_adb(self) -> None:
        self.btn_dl.state(["disabled"])
        self.var_setup.set("Downloading...")
        self.bg(lambda: AdbClient.download_platform_tools(lambda got, total: self.events.put(("dl", got, total))),
                self._adb_downloaded, self._download_failed)

    def _adb_downloaded(self, path: str) -> None:
        self.btn_dl.state(["!disabled"])
        if self._verify(path):
            self._enter_main(path)
        else:
            self.var_setup.set("Cannot run adb.exe. Choose another file with Browse adb.exe.")

    def _download_failed(self, exc: Exception) -> None:
        self.btn_dl.state(["!disabled"])
        self.var_setup.set(str(exc))

    def _browse_adb(self) -> None:
        path = filedialog.askopenfilename(title="Choose adb.exe", filetypes=[("adb.exe", "adb.exe"), ("All", "*.*")])
        if not path:
            return
        if self._verify(path):
            self._enter_main(path)
        else:
            self.var_setup.set("Could not run this file. Choose the correct adb.exe.")

    # ================================================================ main layout
    def _build_main(self) -> None:
        m = self.main = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        m.columnconfigure(0, weight=1)
        m.rowconfigure(2, weight=1)

        box = ttk.LabelFrame(m, text="APK file")
        box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.drop = tk.Label(box, text="Drop an APK file here, or click to choose one"
                             if self.dnd else "Click to choose an APK file\n(drag & drop needs tkinterdnd2)",
                             font=(FONT, 12), bg="#e6f0fb", fg="#0d47a1", relief="groove", cursor="hand2", pady=14)
        self.drop.pack(fill="x", padx=6, pady=6)
        self.drop.bind("<Button-1>", lambda _e: self.pick_apks())
        self.apk_box = ttk.Frame(box)
        self.apk_box.pack(fill="x", padx=6, pady=(0, 4))
        if self.dnd:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

        bar = ttk.Frame(m)
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Label(bar, text="Device", font=(FONT, 11, "bold")).pack(side="left", padx=(0, 10))
        for text, val in (("All", "all"), ("USB only", "usb"), ("Wi-Fi only", "wifi")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.filter, style="Toolbutton",
                            command=self._render_table).pack(side="left", padx=2)
        ttk.Button(bar, text="Select all", command=self.select_all).pack(side="left", padx=(14, 2))
        ttk.Button(bar, text="None", command=self.select_none).pack(side="left", padx=2)

        wrap = ttk.Frame(m)
        wrap.grid(row=2, column=0, sticky="nsew", pady=6)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        cols = ("chk", "conn", "phone", "inst", "plan", "status")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="none")
        for col, text, width in (("chk", "", 40), ("conn", "Connection", 80), ("phone", "Phone (Model / Serial)", 230),
                                 ("inst", "Installed version", 140), ("plan", "Plan", 130),
                                 ("status", "Status", 320)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w", stretch=col in ("phone", "status"))
        for tag, color in COLORS.items():
            self.tree.tag_configure(tag, foreground=color)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self._on_click)

        det = ttk.Frame(m)
        det.grid(row=3, column=0, sticky="ew")
        self.detail = ttk.Label(det, text="", wraplength=760, justify="left", foreground=COLORS["bad"])
        self.detail.pack(side="left", fill="x", expand=True)
        self.copy_btn = ttk.Button(det, text="Copy error", command=self.copy_error)

        run = ttk.Frame(m)
        run.grid(row=4, column=0, sticky="ew", pady=8)
        run.columnconfigure(2, weight=1)
        self.install_btn = ttk.Button(run, text="Install", style="Go.TButton", command=self.on_install)
        self.install_btn.grid(row=0, column=0)
        self.cancel_btn = ttk.Button(run, text="Cancel", command=self.on_cancel)
        self.cancel_btn.grid(row=0, column=1, padx=8)
        self.cancel_btn.grid_remove()
        prog = ttk.Frame(run)
        prog.grid(row=0, column=2, sticky="ew", padx=14)
        self.pbar = ttk.Progressbar(prog, mode="determinate")
        self.pbar.pack(fill="x")
        self.ptext = ttk.Label(prog, text="0 / 0 done")
        self.ptext.pack(anchor="w")

        self.status_lbl = tk.Label(m, text="Choose an APK, tick the phones, then press Install.", font=(FONT, 13),
                                   bg="#e6f0fb", fg="#0d47a1", anchor="w", padx=12, pady=10)
        self.status_lbl.grid(row=5, column=0, sticky="ew")

        self.result_bar = ttk.Frame(m)
        self.result_bar.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self.btn_retry = ttk.Button(self.result_bar, text="Retry failed", command=self.retry_failed)
        self.btn_sig = ttk.Button(self.result_bar, text="Uninstall old and retry",
                                  command=self.retry_signature)
        self.btn_down = ttk.Button(self.result_bar, text="Try downgrade (-r -d)", command=self.retry_downgrade)
        self.btn_csv = ttk.Button(self.result_bar, text="CSV Export", command=self.export_csv)
        self.result_bar.grid_remove()

        self._build_advanced(m)

    def _build_advanced(self, parent: ttk.Frame) -> None:
        nb = self.adv = ttk.Notebook(parent)
        nb.grid(row=7, column=0, sticky="ew", pady=(8, 0))

        opt = ttk.Frame(nb, padding=8)
        nb.add(opt, text="Install options")
        row = ttk.Frame(opt)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="Grant all permissions (-g)", variable=self.var_grant, command=self._opts_changed).pack(side="left", padx=6)
        ttk.Checkbutton(row, text="Force reinstall", variable=self.var_force, command=self._opts_changed).pack(side="left", padx=6)
        ttk.Checkbutton(row, text="Auto-install on new phones", variable=self.var_auto, command=self._auto_toggled).pack(side="left", padx=6)
        ttk.Label(row, text="Workers (1-10):").pack(side="left", padx=(12, 2))
        ttk.Spinbox(row, from_=1, to=10, width=4, textvariable=self.var_workers).pack(side="left")
        ttk.Label(opt, text="Command preview:").pack(anchor="w", pady=(8, 0))
        ttk.Entry(opt, textvariable=self.var_cmd, state="readonly", font=("Consolas", 9)).pack(fill="x")
        row2 = ttk.Frame(opt)
        row2.pack(fill="x", pady=6)
        ttk.Button(row2, text="Restart ADB", command=self.restart_adb).pack(side="left", padx=3)
        ttk.Button(row2, text="Fix problems", command=self.fix_problems).pack(side="left", padx=3)
        ttk.Button(row2, text="CSV Export", command=self.export_csv).pack(side="left", padx=3)
        ttk.Button(row2, text="Reset auto-install list", command=self.reset_handled).pack(side="left", padx=3)

        apps = ttk.Frame(nb, padding=8)
        nb.add(apps, text="Apps")
        r1 = ttk.Frame(apps)
        r1.pack(fill="x")
        ttk.Label(r1, text="Phone:").pack(side="left")
        self.app_phone_cb = ttk.Combobox(r1, textvariable=self.var_app_phone, state="readonly", width=44,
                                         postcommand=self.refresh_app_phones)
        self.app_phone_cb.pack(side="left", padx=6)
        ttk.Button(r1, text="Load apps", command=self.load_apps).pack(side="left", padx=3)
        r2 = ttk.Frame(apps)
        r2.pack(fill="x", pady=(6, 0))
        for text, val in (("User apps", "user"), ("System apps", "system"),
                          ("Disabled", "disabled"), ("All", "all")):
            ttk.Radiobutton(r2, text=text, value=val, variable=self.var_app_scope).pack(side="left", padx=(0, 8))
        r3 = ttk.Frame(apps)
        r3.pack(fill="x", pady=(6, 0))
        ttk.Label(r3, text="Search:").pack(side="left")
        ttk.Entry(r3, textvariable=self.var_search, width=26).pack(side="left", padx=6)
        self.var_search.trace_add("write", lambda *_: self._filter_apps())
        ttk.Button(r3, text="Select all", command=lambda: self.apps_list.select_set(0, "end")).pack(side="left", padx=3)
        ttk.Button(r3, text="Uninstall", command=lambda: self.app_action("uninstall")).pack(side="left", padx=3)
        ttk.Button(r3, text="Clear data", command=lambda: self.app_action("clear")).pack(side="left", padx=3)
        self.apps_count = ttk.Label(apps, text="")
        self.apps_count.pack(anchor="w", pady=(6, 0))
        lf = ttk.Frame(apps)
        lf.pack(fill="both", expand=True, pady=4)
        self.apps_list = tk.Listbox(lf, height=10, selectmode="extended", exportselection=False, font=("Consolas", 10))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.apps_list.yview)
        self.apps_list.config(yscrollcommand=sb.set)
        self.apps_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        nb.add(build_wireless_tools(self, nb), text="Wireless")

        logf = ttk.Frame(nb, padding=8)
        nb.add(logf, text="Log")
        self.log_text = tk.Text(logf, height=8, bg="#10161c", fg="#aab4be", font=("Consolas", 9), state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        for tag, color in (("cmd", "#9aa5b1"), ("ok", "#5fd38d"), ("bad", "#ff7b70")):
            self.log_text.tag_configure(tag, foreground=color)
        lrow = ttk.Frame(logf)
        lrow.pack(fill="x", pady=(4, 0))
        ttk.Button(lrow, text="Copy log", command=self.copy_log).pack(side="left", padx=3)
        ttk.Button(lrow, text="Clear log", command=self.clear_log).pack(side="left", padx=3)

    def apply_mode(self) -> None:
        advanced = self.mode.get() == "advanced"
        if advanced:
            self.adv.grid()
        else:
            self.adv.grid_remove()
            self.var_auto.set(False)
        self.settings.set("mode", self.mode.get())
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
        look = {"info": ("#e6f0fb", "#0d47a1", 13, "normal"), "ok": ("#1b7f3b", "white", 18, "bold"),
                "bad": ("#fde8e8", "#c62828", 13, "bold")}[kind]
        self.status_lbl.config(text=text, bg=look[0], fg=look[1], font=(FONT, look[2], look[3]))

    def log(self, text: str, tag: str = "") -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n", tag)
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 2000:
            self.log_text.delete("1.0", f"{lines - 2000}.0")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def copy_log(self) -> None:
        self._clip(self.log_text.get("1.0", "end"))

    def clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _clip(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def copy_error(self) -> None:
        self._clip(self.raw_errors.get(self.detail_key, ""))

    def dev_by_key(self, key: str) -> Optional[Device]:
        return next((d for d in self.devices if d.key == key), None)

    def ticked(self) -> list[Device]:
        return [d for d in self.devices if d.key in self.checked and d.usable]

    def pick_usb_device(self) -> Optional[Device]:
        usb = [d for d in self.devices if d.usable and d.conn == "USB"]
        ticked = [d for d in usb if d.key in self.checked]
        if len(ticked) == 1:
            return ticked[0]
        if len(usb) == 1:
            return usb[0]
        messagebox.showinfo("USB phone", "Tick exactly one USB phone (or plug in only one phone).")
        return None

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
                if self.wizard:
                    self.wizard.on_pair_event(ev[1], ev[2])
            elif kind == "dl":
                got, total = ev[1], ev[2]
                self.dl_bar["value"] = (got * 100 / total) if total else 0
                self.var_setup.set(f"Downloading: {got / 1048576:.1f} / {total / 1048576:.1f} MB" if total else f"Downloading: {got / 1048576:.1f} MB")
        except Exception as exc:     # a UI handler must never kill the loop
            logging.exception("event %s failed", kind)
            self.log(f"UI error ({kind}): {exc}", "bad")

    def _show_error(self, exc: Exception) -> None:
        self.set_status(f"Error: {exc}", "bad")
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
        if self.wizard:
            self.wizard.on_devices(devs)
        if self.var_auto.get():
            new = [d for d in devs if d.usable and d.key not in self.handled]
            if new and not self.groups:
                self.set_status("Auto-install is on. Choose an APK first.", "bad")
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
        return "Not installed" if val is None else fmt_version(val)

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
        return action, label + (f" (+{extra})" if extra > 0 else "")

    def _render_table(self) -> None:
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
                text = label + (("\n" + (detail[:70] + "…" if len(detail) > 70 else detail)) if detail else "")
            else:
                text, tag = "", "gray"
            chk = "☑" if d.key in self.checked else ("☐" if d.usable else "✕")
            conn = d.conn + (" (+Wi-Fi)" if d.alts and d.conn == "USB" else "")
            data.append((d.key, (chk, conn, f"{d.model}\n{d.serial}", self._inst_text(d), self._plan_action(d)[1], text), tag))
        if data == self.last_rows:
            return
        self.last_rows = data
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for key, vals, tag in data:
            self.tree.insert("", "end", iid=key, values=vals, tags=(tag,))
        self.tree.yview_moveto(top)

    def _on_click(self, event: Any) -> str:
        key = self.tree.identify_row(event.y)
        dev = self.dev_by_key(key) if key else None
        if dev:
            if dev.usable:
                self.checked.symmetric_difference_update({key})
                self._update_preview()
            self._show_detail(key)
            self._render_table()
        return "break"

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

    def _opts_changed(self) -> None:
        self.settings.set("grant", self.var_grant.get())
        self.settings.set("force", self.var_force.get())
        self._render_table()
        self._update_preview()

    # ================================================================ APKs
    def pick_apks(self) -> None:
        start = self.settings.get("last_apk_dir") or None
        paths = filedialog.askopenfilenames(title="Choose APK", initialdir=start,
                                            filetypes=[("APK", "*.apk"), ("All files", "*.*")])
        if paths:
            self.add_apks(list(paths))

    def _on_drop(self, event: Any) -> None:
        self.add_apks(list(self.root.tk.splitlist(event.data)))

    def add_apks(self, paths: list[str]) -> None:
        if self.main.winfo_ismapped() == 0:
            return
        bundles = [Path(p).name for p in paths if Path(p).suffix.lower() in (".apks", ".xapk", ".aab")]
        if bundles:
            messagebox.showinfo("This format cannot be installed directly",
                                "These files cannot be installed directly:\n" + "\n".join(bundles) +
                                "\n\nFirst extract them like a ZIP and give the .apk files inside.")
        have = {a.path for a in self.apks}
        good = [p for p in paths if Path(p).suffix.lower() == ".apk" and p not in have]
        if not good:
            return
        self.settings.set("last_apk_dir", str(Path(good[0]).parent))
        self.set_status("Reading APK...")
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
                    "Split APK?", f"{pkg} has {len(lst)} files.\nAre these split APKs of the same app? (adb install-multiple will be used)")
        self._apks_changed()
        if unreadable:
            self.set_status("Could not read APK info (run pip install pyaxmlparser or keep aapt available). The package name will be asked at install time.")

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

    def _apks_changed(self) -> None:
        self.groups = self._build_groups()
        for child in self.apk_box.winfo_children():
            child.destroy()
        for a in self.apks:
            row = ttk.Frame(self.apk_box)
            row.pack(fill="x", pady=1)
            split = " [split]" if a.package and self.split_choice.get(a.package) else ""
            vc = a.version_code if a.version_code is not None else "?"
            ttk.Label(row, text=f"{a.name}{split}   |   {a.package or 'unknown package'}   |   "
                                f"versionName {a.version_name or '?'}   |   versionCode {vc}").pack(side="left")
            ttk.Button(row, text="✕", width=3, command=lambda p=a.path: self.remove_apk(p)).pack(side="right")
        self.plan_gen += 1
        self.installed.clear()
        self.checking.clear()
        self._ensure_plans()
        self._render_table()
        self._update_preview()
        self.set_status("APK ready. Tick the phones and press Install." if self.apks else "Choose an APK, tick the phones, then press Install.")

    # ================================================================ install
    def _ask_missing_packages(self) -> bool:
        for apk in self.apks:
            if not apk.package:
                name = simpledialog.askstring("Package name", f"Enter the package name of {apk.name} (for example com.example.app):")
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
        return JobOptions(self.var_grant.get(), self.var_force.get(), workers, replace, targets or {})

    def on_install(self) -> None:
        if self.manual_batch is not None:
            return
        if not self.groups:
            self.set_status("Choose an APK first.", "bad")
            return
        devices = self.ticked()
        if not devices:
            self.set_status("Tick at least one phone.", "bad")
            return
        if not self._ask_missing_packages():
            return
        self.start_batch(devices, "normal")

    def start_batch(self, devices: list[Device], mode: str, auto: bool = False,
                    replace: bool = False, targets: Optional[dict[str, set[str]]] = None) -> None:
        self.batch_id += 1
        bid = self.batch_id
        self.batches[bid] = {"total": len(devices), "results": [], "auto": auto}
        self.help_shown = False
        for d in devices:
            self.status[d.key] = ("waiting", "")
            self.handled.add(d.key)
        if not auto:
            self.manual_batch = bid
            self.install_btn.state(["disabled"])
            self.cancel_btn.grid()
            self.result_bar.grid_remove()
            self.pbar["value"] = 0
            self.ptext.config(text=f"0 / {len(devices)} done")
            self.set_status("Installing... keep the phones unlocked.")
        self._render_table()
        self.installer.start(bid, devices, self.groups, self._options(replace, targets), mode)

    def on_cancel(self) -> None:
        if self.manual_batch is not None:
            self.installer.cancel(self.manual_batch)
            self.set_status("Cancelling... running jobs will finish first.")

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
        self.log(f"{res.name} ({res.serial}): {label} {res.detail}".rstrip(), "ok" if res.status in ("success", "skipped") else "bad")
        if res.brand_help and not self.help_shown:
            self.help_shown = True
            show_brand_help(self, brand_key(res.manufacturer))
        self._render_table()

    def _on_progress(self, bid: int, done: int, total: int) -> None:
        if bid == self.manual_batch:
            self.pbar["value"] = done * 100 / max(total, 1)
            self.ptext.config(text=f"{done} of {total} done")

    def _on_batch_done(self, bid: int) -> None:
        batch = self.batches.pop(bid, None)
        if not batch:
            return
        results: list[JobResult] = batch["results"]
        for r in results:
            self.installed.pop(r.key, None)
        self._ensure_plans()
        if batch["auto"]:
            self._auto_done(results[0] if results else None)
            return
        self.manual_batch = None
        self.install_btn.state(["!disabled"])
        self.cancel_btn.grid_remove()
        ok = sum(r.status == "success" for r in results)
        bad = sum(r.status in ("failed", "sig") for r in results)
        skip = sum(r.status in ("skipped", "older") for r in results)
        self.set_status(f"{ok} success, {bad} failed, {skip} skipped", "ok" if bad == 0 else "bad")
        beep("ok" if bad == 0 else "bad")
        self._update_result_bar()

    def _auto_done(self, res: Optional[JobResult]) -> None:
        if res and res.status in ("success", "skipped"):
            self.set_status("✔ Done - plug in the next phone", "ok")
            beep("auto")
        elif res:
            self.set_status(f"{res.name}: {res.detail or 'Failed'}", "bad")
            beep("bad")

    # ---------- follow-up actions ----------
    def _keys_with(self, code: str) -> list[Device]:
        return [d for d in self.devices if d.usable and self.status.get(d.key, ("", ""))[0] == code]

    def _update_result_bar(self) -> None:
        for btn in (self.btn_retry, self.btn_sig, self.btn_down, self.btn_csv):
            btn.pack_forget()
        shown = False
        for btn, code in ((self.btn_retry, "failed"), (self.btn_sig, "sig"), (self.btn_down, "older")):
            if self._keys_with(code):
                btn.pack(side="left", padx=3)
                shown = True
        if self.history:
            self.btn_csv.pack(side="left", padx=3)
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
        if messagebox.askyesno("Confirm", f"App: {', '.join(pkgs)}\nPhones:\n{names}\n\n"
                               "The old app will be uninstalled and the new one installed.\n"
                               "Warning: all data of this app will be erased!\n\nContinue?", icon="warning"):
            self.start_batch(devs, "uninstall_retry", targets=self._targets(devs))

    def retry_downgrade(self) -> None:
        devs = self._keys_with("older")
        if not devs or self.manual_batch is not None:
            return
        names = "\n".join(f"  • {d.model} ({d.serial})" for d in devs)
        if messagebox.askyesno("Downgrade", f"Phones:\n{names}\n\nWill try to install the older version with -r -d.\n"
                               "Note: Android usually allows downgrade only for debuggable apps, so this may fail.\n"
                               "Then you must Uninstall and install the older version, which erases the app data.\n\nTry it?", icon="warning"):
            self.start_batch(devs, "downgrade", targets=self._targets(devs))

    def export_csv(self) -> None:
        if not self.history:
            messagebox.showinfo("CSV", "There are no results yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="apk-install-results.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["Phone", "Connection", "Serial", "Old version", "New version", "Result", "Time"])
                for r in self.history:
                    w.writerow([r.name, r.conn, r.serial, r.old, r.new, f"{r.status} {r.detail}".strip(), r.when])
            self.set_status(f"CSV saved: {path}")
        except OSError as exc:
            messagebox.showerror("CSV", f"Could not write the file: {exc}")

    # ================================================================ auto-install
    def _auto_toggled(self) -> None:
        if self.var_auto.get():
            self.handled |= {d.key for d in self.devices if d.usable}   # only NEW phones count
            self.set_status("Auto-install is on. From now on, every new phone you plug in will be installed.")

    def reset_handled(self) -> None:
        self.handled.clear()
        self.set_status("Auto-install list reset (all phones will count as new again).")

    # ================================================================ advanced tools
    def restart_adb(self) -> None:
        def work() -> str:
            self.adb.kill_server()
            self.adb.start_server()
            self.devman.refresh_now()
            return "ADB restarted."
        self.bg(work, lambda msg: self.set_status(msg))

    def fix_problems(self) -> None:
        self.set_status("Finding and fixing problems...")

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
                    lines.append(f"• {p.get('name', '?')} ({p.get('addr')}): not connected - Wireless debugging ON? Same Wi-Fi? "
                                 "AP isolation off on the router? If needed, pair again from Add phone.")
            return "\n".join(lines) or "All phones are fine ✔"

        self.bg(work, self._fix_done)

    def _fix_done(self, report: str) -> None:
        self.set_status("Fix problems finished.")
        win = tk.Toplevel(self.root)
        win.title("Problem fix report")
        win.geometry("640x320")
        txt = tk.Text(win, wrap="word", font=(FONT, 11), padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", report)
        txt.config(state="disabled")

    def refresh_app_phones(self) -> None:
        self.app_phone_map = {f"{d.model or d.serial} · {d.conn} · {d.serial}": d for d in self.devices if d.usable}
        labels = list(self.app_phone_map)
        self.app_phone_cb["values"] = labels
        if self.var_app_phone.get() not in labels:
            ticked = self.ticked()
            pick = next((lb for lb, d in self.app_phone_map.items() if ticked and d.key == ticked[0].key),
                        labels[0] if labels else "")
            self.var_app_phone.set(pick)

    def load_apps(self) -> None:
        self.refresh_app_phones()
        dev = self.app_phone_map.get(self.var_app_phone.get())
        if not dev:
            messagebox.showinfo("Apps", "No phone found. Add a phone first.")
            return
        scope = self.var_app_scope.get()
        self.set_status(f"{dev.model or dev.serial}: loading the app list...")
        self.bg(lambda: self.adb.list_packages(dev.serial, scope),
                lambda pkgs: self._apps_loaded(pkgs, dev, scope))

    def _apps_loaded(self, pkgs: list[str], dev: Device, scope: str) -> None:
        self.all_pkgs = pkgs
        self.apps_dev = dev
        self.apps_scope = scope
        self.set_status(f"{dev.model or dev.serial}: found {len(pkgs)} app(s).")
        self._filter_apps()

    def _filter_apps(self) -> None:
        q = self.var_search.get().strip().lower()
        self.apps_list.delete(0, "end")
        for pkg in self.all_pkgs:
            if q in pkg.lower():
                self.apps_list.insert("end", pkg)
        self.apps_count.config(text=f"Showing {self.apps_list.size()} / total {len(self.all_pkgs)}")

    def app_action(self, kind: str) -> None:
        sel = self.apps_list.curselection()
        dev = self.apps_dev
        if not sel or dev is None:
            messagebox.showinfo("Apps", "Load the apps first, then select one or more apps.")
            return
        pkgs = [self.apps_list.get(i) for i in sel]
        system = self.apps_scope in ("system", "disabled")
        verb = "Uninstall" if kind == "uninstall" else "Clear data"
        shown = "\n".join(f"  • {p}" for p in pkgs[:12]) + (f"\n  ... and {len(pkgs) - 12} more" if len(pkgs) > 12 else "")
        warn = "Warning: all data of the app will be erased!"
        if system and kind == "uninstall":
            warn = ("Warning: these are system apps. Removing the wrong app can break calls, network or settings on the phone.\n"
                    "The app is removed for the current user only; a factory reset brings it back.")
        if not messagebox.askyesno("Confirm",
                                   f"{verb} - {len(pkgs)} app(s)\nPhone: {dev.model or dev.serial} ({dev.serial})\n\n{shown}\n\n{warn}\n\nContinue?",
                                   icon="warning"):
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
        self.set_status(f"Done. {len(lines) - failed} succeeded, {failed} failed. Details are in the Log tab.",
                        "bad" if failed else "info")

    # ================================================================ wizard / close
    def open_wizard(self) -> None:
        if self.wizard is not None:
            self.wizard.win.lift()
            return
        self.wizard = Wizard(self)

    def on_close(self) -> None:
        try:
            self.settings.set("geometry", self.root.geometry())
            self.settings.set("mode", self.mode.get())
            self.settings.save()
        finally:
            self.devman.stop()
            self.pairing.stop()
            self.root.destroy()
