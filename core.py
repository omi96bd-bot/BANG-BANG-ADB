"""BANG BANG ADB core: all the logic, no window code. The page web/index.html is the user interface.
JavaScript calls the public methods of Core (through pywebview) and receives events with emit()."""
from __future__ import annotations

import base64
import csv
import io
import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import installer as installer_mod
from adb_client import AdbClient
from devices import Device, DeviceManager
from help_text import BRANDS, BRANDS_BN, brand_key
from i18n import BN
from installer import ApkGroup, ApkInfo, ApkReader, Installer, JobOptions, JobResult, fmt_version
from pairing import PairingService
from settings import Settings, app_dir

try:
    import webview
except Exception:                      # only needed when a window exists
    webview = None

STATUS = {"waiting": "mute", "checking": "acc", "installing": "acc", "success": "ok", "failed": "bad",
          "skipped": "mute", "sig": "bad", "older": "warn"}
BOOLS = ("animations", "sound", "wake_screen", "stay_awake", "skip_verifier", "retry_once", "open_after",
         "confirm_uninstall", "auto_csv", "front_when_done", "log_popup", "reconnect_saved", "remember_dir",
         "grant", "force")
UNKNOWN, ERROR = "?", "err"


class Core:
    def __init__(self) -> None:
        self.settings = Settings()
        self.events: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self.window: Any = None
        self.ready = False
        self.stop_flag = False
        self.dirty = True
        # state
        self.devices: list[Device] = []
        self.checked: set[str] = set()
        self.seen: set[str] = set()
        self.handled: set[str] = set()
        self.apks: list[ApkInfo] = []
        self.groups: list[ApkGroup] = []
        self.split_choice: dict[str, bool] = {}
        self.pending_split: list[str] = []
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
        self.auto = False
        self.adb_ok = False
        self.msg: dict[str, Any] = {"key": "Choose an APK, tick the phones, then press Install.", "params": {}, "kind": "info"}
        self.progress = {"done": 0, "total": 0, "running": False}
        self.finish = {"n": 0, "bad": 0}
        self.log_buffer: list[dict[str, str]] = []
        self.dl = {"got": 0, "total": 0}
        self.missing_pkgs = PairingService.missing_packages()
        installer_mod.INSTALL_TIMEOUT = int(self.settings.get("timeout"))
        # services
        self.adb = AdbClient(None, lambda text, tag: self.events.put(("log", text, tag)))
        self.reader = ApkReader()
        self.devman = DeviceManager(self.adb, self.settings, self.events)
        self.installer = Installer(self.adb, self.events)
        self.pairing = PairingService(self.adb, self.events)

    # ================================================================ window glue
    def attach(self, window: Any) -> None:
        self.window = window
        try:
            window.events.loaded += self._page_loaded
            window.events.closing += self._closing
        except Exception:
            logging.exception("window events")

    def _page_loaded(self) -> None:
        try:                                         # drag and drop gives real file paths (pywebview 5+)
            from webview.dom import DOMEventHandler
            self.window.dom.document.events.drop += DOMEventHandler(self._on_drop, True, True)
        except Exception:
            logging.info("drag and drop is not available in this pywebview version")

    def _on_drop(self, event: dict) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            self.add_apks(paths)

    def _closing(self) -> None:
        self.stop_flag = True
        try:
            self.devman.stop()
            self.pairing.stop()
            self.settings.save()
        except Exception:
            logging.exception("closing")

    def start(self) -> None:
        """Called once, after the window is shown."""
        threading.Thread(target=self._pump, daemon=True).start()
        path = AdbClient.find_adb(self.settings.get("adb_path"))
        if path and self._verify(path):
            self._enter_main(path)
        self.dirty = True

    def emit(self, name: str, data: Any = None) -> None:
        import json
        if self.window is None or not self.ready:
            return
        try:
            self.window.evaluate_js("window.bb&&window.bb.on(%s,%s)" % (json.dumps(name), json.dumps(data)))
        except Exception:
            logging.exception("emit %s", name)

    def toast(self, key: str, kind: str = "info", **params: Any) -> None:
        self.emit("toast", {"key": key, "params": params, "kind": kind})

    def set_status(self, key: str, kind: str = "info", **params: Any) -> None:
        self.msg = {"key": key, "params": params, "kind": kind}
        self.dirty = True

    def log(self, text: str, tag: str = "") -> None:
        self.log_buffer.append({"text": text, "tag": tag})
        if len(self.log_buffer) > 1500:
            del self.log_buffer[:300]
        self.emit("log", {"text": text, "tag": tag})

    def bg(self, fn: Callable[[], Any], done: Optional[Callable[[Any], None]] = None,
           on_error: Optional[Callable[[Exception], None]] = None) -> None:
        def work() -> None:
            try:
                result: Any = fn()
            except Exception as exc:
                logging.exception("background task")
                result = exc
            if done is not None or isinstance(result, Exception):
                self.events.put(("cb", done, on_error, result))

        threading.Thread(target=work, daemon=True).start()

    def ui(self, fn: Callable[[], None]) -> None:
        self.events.put(("cb", lambda _r: fn(), None, None))

    # ================================================================ event pump
    def _pump(self) -> None:
        last = 0.0
        while not self.stop_flag:
            try:
                ev = self.events.get(timeout=0.1)
            except queue.Empty:
                ev = None
            n = 0
            while ev is not None and n < 300:
                with self.lock:
                    self._handle(ev)
                n += 1
                try:
                    ev = self.events.get_nowait()
                except queue.Empty:
                    ev = None
            if self.dirty and time.time() - last > 0.08:
                with self.lock:
                    self.dirty = False
                    snap = self.snapshot()
                self.emit("state", snap)
                last = time.time()

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
                self.set_status("{err}", "bad", err=ev[1])
            elif kind == "inst":
                self._on_inst(ev[1], ev[2], ev[3])
            elif kind == "row_state":
                self.status[ev[2]] = (ev[3], ev[4])
                self.dirty = True
            elif kind == "row":
                self._on_row(ev[1], ev[2])
            elif kind == "progress":
                self._on_progress(ev[1], ev[2], ev[3])
            elif kind == "batch_done":
                self._on_batch_done(ev[1])
            elif kind == "pair":
                self.emit("pair", {"kind": ev[1], "text": ev[2]})
                if ev[1] == "ok":
                    self.devman.refresh_now()
            elif kind == "dl":
                self.dl = {"got": round(ev[1] / 1048576, 1), "total": round(ev[2] / 1048576, 1)}
                self.dirty = True
        except Exception as exc:
            logging.exception("event %s failed", kind)
            self.log(f"UI error ({kind}): {exc}", "bad")

    def _show_error(self, exc: Exception) -> None:
        self.set_status("Error: {err}", "bad", err=str(exc))
        self.log(f"Error: {exc}", "bad")

    # ================================================================ snapshot for the page
    def _inst_text(self, d: Device) -> str:
        if not d.usable:
            return "—"
        val = self.installed.get(d.key, UNKNOWN)
        if val == UNKNOWN:
            return "…" if self.groups else "—"
        if val == ERROR:
            return "?"
        return "Not installed" if val is None else fmt_version(val)

    def _plan_text(self, d: Device) -> tuple[str, str]:
        if not d.usable or not self.groups:
            return "", "—"
        val = self.installed.get(d.key, UNKNOWN)
        if val == UNKNOWN:
            return "", "…"
        if val == ERROR:
            return "", "?"
        action, label = Installer.plan(self.groups[0], val, bool(self.settings.get("force")))
        return action, label + (f" (+{len(self.groups) - 1})" if len(self.groups) > 1 else "")

    def _keys_with(self, code: str) -> list[Device]:
        return [d for d in self.devices if d.usable and self.status.get(d.key, ("", ""))[0] == code]

    def snapshot(self) -> dict[str, Any]:
        devs = []
        for d in self.devices:
            code, detail = self.status.get(d.key, ("", ""))
            devs.append({"key": d.key, "model": d.model or d.serial, "serial": d.serial,
                         "conn": d.conn, "wifi_too": bool(d.alts and d.conn == "USB"), "usable": d.usable,
                         "state": d.state, "reason": d.reason, "checked": d.key in self.checked,
                         "installed": self._inst_text(d), "plan": self._plan_text(d)[1],
                         "code": code, "detail": detail, "color": STATUS.get(code, "mute"),
                         "busy": code in ("checking", "installing"), "has_raw": bool(self.raw_errors.get(d.key))})
        live = {d.serial for d in self.devices} | {a for d in self.devices for a in d.alts}
        saved = [{"key": p.get("key", ""), "name": p.get("name", "?"), "addr": p.get("addr", "")}
                 for p in self.settings.saved_phones()
                 if p.get("addr") not in live and not any(d.key == p.get("key") for d in self.devices)]
        first = next((d for d in self.devices if d.key in self.checked and d.usable), None)
        paths = self.groups[0].paths if self.groups else [r"C:\path\app.apk"]
        replace = (self._plan_text(first)[0] in ("update", "reinstall", "")) if first else True
        cmd = self.adb.preview(first.serial if first else "SERIAL", paths, bool(self.settings.get("grant")), replace, False)
        sig = self._keys_with("sig")
        older = self._keys_with("older")
        opts = {k: self.settings.get(k) for k in BOOLS}
        opts.update({"workers": self.settings.get("workers"), "timeout": self.settings.get("timeout"),
                     "lang": self.settings.get("lang"), "theme": self.settings.get("theme"), "auto": self.auto,
                     "adb_path": self.settings.get("adb_path")})
        return {"adb_ok": self.adb_ok, "devices": devs, "saved_offline": saved, "cmd": cmd, "opts": opts,
                "apks": [{"path": a.path, "name": a.name, "package": a.package, "vname": a.version_name,
                          "vcode": a.version_code, "split": bool(a.package and self.split_choice.get(a.package))}
                         for a in self.apks],
                "msg": self.msg, "progress": self.progress, "busy": self.manual_batch is not None,
                "finish": self.finish, "dl": self.dl,
                "fail_n": len(self._keys_with("failed")), "sig": [d.model or d.serial for d in sig],
                "sig_pkgs": sorted({self.pkg_of.get(d.key, "?") for d in sig}),
                "older": [d.model or d.serial for d in older], "has_history": bool(self.history),
                "missing_pkgs": self.missing_pkgs}

    # ================================================================ calls from the page
    def boot(self) -> dict[str, Any]:
        self.ready = True
        self.dirty = True
        brands = [{"key": k, "name": v[0], "steps": v[1], "steps_bn": BRANDS_BN.get(k, v[1])} for k, v in BRANDS.items()]
        with self.lock:
            snap = self.snapshot()
        return {"state": snap, "bn": BN, "log": self.log_buffer[-500:], "brands": brands}

    def set_option(self, key: str, value: Any) -> None:
        with self.lock:
            if key == "auto":
                self.auto = bool(value)
                if self.auto:
                    self.handled |= {d.key for d in self.devices if d.usable}
                    self.set_status("Auto-install is on. From now on, every new phone you plug in will be installed.")
            elif key in BOOLS:
                self.settings.set(key, bool(value))
            elif key == "workers":
                self.settings.set(key, max(1, min(10, int(value))))
            elif key == "timeout":
                v = max(30, min(900, int(value)))
                self.settings.set(key, v)
                installer_mod.INSTALL_TIMEOUT = v
            elif key in ("lang", "theme"):
                self.settings.set(key, str(value))
            self.settings.save()
            self.dirty = True

    # ---------- phones ----------
    def refresh_all(self) -> None:
        with self.lock:
            self.installed.clear()
            self.checking.clear()
            self.plan_gen += 1
        self.devman.refresh_now()
        self.toast("Refreshing phones...")

    def toggle_check(self, key: str) -> None:
        with self.lock:
            dev = next((d for d in self.devices if d.key == key), None)
            if dev and dev.usable:
                self.checked.symmetric_difference_update({key})
            self.dirty = True

    def select_all(self, keys: list[str]) -> None:
        with self.lock:
            self.checked |= {d.key for d in self.devices if d.usable and d.key in keys}
            self.dirty = True

    def select_none(self) -> None:
        with self.lock:
            self.checked.clear()
            self.dirty = True

    def raw_error(self, key: str) -> str:
        return self.raw_errors.get(key, "")

    def _on_devices(self, devs: list[Device]) -> None:
        self.devices = devs
        keys = {d.key for d in devs}
        for d in devs:
            if d.usable and d.key not in self.seen:
                self.seen.add(d.key)
                self.checked.add(d.key)           # new phones start ticked
        self.checked &= keys
        self._ensure_plans()
        self.dirty = True
        if self.auto:
            new = [d for d in devs if d.usable and d.key not in self.handled]
            if new and not self.groups:
                self.set_status("Auto-install is on. Choose an APK first.", "bad")
            else:
                for d in new:
                    self.start_batch([d], "normal", auto=True)

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
        self.dirty = True

    # ---------- APKs ----------
    def pick_apks(self) -> None:
        if webview is None or self.window is None:
            return
        start = (self.settings.get("last_apk_dir") if self.settings.get("remember_dir") else "") or ""
        kind = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
        paths = self.window.create_file_dialog(kind, directory=start, allow_multiple=True,
                                               file_types=("APK files (*.apk)", "All files (*.*)"))
        if paths:
            self.add_apks(list(paths))

    def add_apks(self, paths: list[str]) -> None:
        if not self.adb_ok:
            return
        bundles = [Path(p).name for p in paths if Path(p).suffix.lower() in (".apks", ".xapk", ".aab")]
        if bundles:
            self.emit("alert", {"title": "This format cannot be installed directly",
                                "body": "These files cannot be installed directly:", "list": bundles,
                                "foot": "First extract them like a ZIP and give the .apk files inside."})
        have = {a.path for a in self.apks}
        good = [p for p in paths if Path(p).suffix.lower() == ".apk" and p not in have]
        if not good:
            return
        if self.settings.get("remember_dir"):
            self.settings.set("last_apk_dir", str(Path(good[0]).parent))
        self.set_status("Reading APK...")
        self.bg(lambda: [self.reader.read(p) for p in good], self._apks_read)

    def _apks_read(self, infos: list[ApkInfo]) -> None:
        self.apks.extend(infos)
        by_pkg: dict[str, list[ApkInfo]] = {}
        for a in self.apks:
            if a.package:
                by_pkg.setdefault(a.package, []).append(a)
        self.pending_split = [p for p, lst in by_pkg.items() if len(lst) > 1 and p not in self.split_choice]
        if any(not i.package for i in infos):
            self.toast("Could not read APK info (run pip install pyaxmlparser or keep aapt available). "
                       "The package name will be asked at install time.", "bad")
        self._ask_next_split(by_pkg)

    def _ask_next_split(self, by_pkg: Optional[dict] = None) -> None:
        if self.pending_split:
            pkg = self.pending_split[0]
            n = sum(1 for a in self.apks if a.package == pkg)
            self.emit("ask_split", {"pkg": pkg, "n": n})
        else:
            self._apks_changed()

    def set_split(self, pkg: str, yes: bool) -> None:
        with self.lock:
            self.split_choice[pkg] = bool(yes)
            self.pending_split = [p for p in self.pending_split if p != pkg]
            self._ask_next_split()

    def set_package(self, path: str, name: str) -> None:
        with self.lock:
            for a in self.apks:
                if a.path == path:
                    a.package = name.strip()
            self.groups = self._build_groups()
            self.dirty = True

    def remove_apk(self, path: str) -> None:
        with self.lock:
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
        self.plan_gen += 1
        self.installed.clear()
        self.checking.clear()
        self._ensure_plans()
        self.set_status("APK ready. Tick the phones and press Install." if self.apks
                        else "Choose an APK, tick the phones, then press Install.")

    # ---------- install ----------
    def install(self) -> dict[str, Any]:
        with self.lock:
            if self.manual_batch is not None:
                return {"ok": False}
            if not self.groups:
                self.set_status("Choose an APK first.", "bad")
                self.toast("Choose an APK first.", "bad")
                return {"ok": False}
            devices = [d for d in self.devices if d.key in self.checked and d.usable]
            if not devices:
                self.set_status("Tick at least one phone.", "bad")
                self.toast("Tick at least one phone.", "bad")
                return {"ok": False}
            for a in self.apks:
                if not a.package:
                    return {"ok": False, "need_pkg": a.path, "name": a.name}
            self.groups = self._build_groups()
            self.start_batch(devices, "normal")
            return {"ok": True}

    def _options(self, replace: bool = False, targets: Optional[dict[str, set[str]]] = None) -> JobOptions:
        installer_mod.INSTALL_TIMEOUT = int(self.settings.get("timeout"))
        return JobOptions(bool(self.settings.get("grant")), bool(self.settings.get("force")),
                          int(self.settings.get("workers")), replace, targets or {})

    def _shell(self, serial: str, *args: str) -> None:
        self.adb.run(["shell", *args], timeout=15, serial=serial)

    def _prep(self, devices: list[Device]) -> None:
        for d in devices:
            try:
                if self.settings.get("wake_screen"):
                    self._shell(d.serial, "input", "keyevent", "KEYCODE_WAKEUP")
                    self._shell(d.serial, "wm", "dismiss-keyguard")
                if self.settings.get("stay_awake"):
                    self._shell(d.serial, "svc", "power", "stayon", "usb")
                if self.settings.get("skip_verifier"):
                    self._shell(d.serial, "settings", "put", "global", "verifier_verify_adb_installs", "0")
            except Exception:
                logging.exception("prep failed for %s", d.serial)

    def _restore(self, serials: list[str]) -> None:
        for ser in serials:
            try:
                if self.settings.get("stay_awake"):
                    self._shell(ser, "svc", "power", "stayon", "false")
                if self.settings.get("skip_verifier"):
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
            self.progress = {"done": 0, "total": len(devices), "running": True}
            self.set_status("Installing... keep the phones unlocked.")
        self.dirty = True
        opts = self._options(replace, targets)

        def go(_r: Any = None) -> None:
            self.installer.start(bid, devices, self.groups, opts, mode)

        if any(self.settings.get(k) for k in ("wake_screen", "stay_awake", "skip_verifier")):
            self.bg(lambda: self._prep(devices), go)
        else:
            go()

    def cancel(self) -> None:
        with self.lock:
            if self.manual_batch is not None:
                if self.manual_batch in self.batches:
                    self.batches[self.manual_batch]["cancelled"] = True
                self.installer.cancel(self.manual_batch)
                self.set_status("Cancelling... running jobs will finish first.")

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
        self.log(f"{res.name} ({res.serial}): {res.status} {res.detail}".rstrip(),
                 "ok" if res.status in ("success", "skipped") else "bad")
        if res.status == "success" and res.package and self.settings.get("open_after"):
            self.bg(lambda: self.adb.run(["shell", "monkey", "-p", res.package, "-c", "android.intent.category.LAUNCHER", "1"],
                                         timeout=15, serial=res.serial))
        if res.brand_help and not self.help_shown:
            self.help_shown = True
            self.emit("brand_help", {"brand": brand_key(res.manufacturer)})
        self.dirty = True

    def _on_progress(self, bid: int, done: int, total: int) -> None:
        if bid == self.manual_batch:
            self.progress = {"done": done, "total": total, "running": done < total}
            self.dirty = True

    def _on_batch_done(self, bid: int) -> None:
        batch = self.batches.pop(bid, None)
        if not batch:
            return
        results: list[JobResult] = batch["results"]
        if any(self.settings.get(k) for k in ("stay_awake", "skip_verifier")):
            self.bg(lambda: self._restore(batch["serials"]))
        for r in results:
            self.installed.pop(r.key, None)
        self._ensure_plans()
        if batch["auto"]:
            res = results[0] if results else None
            if res and res.status in ("success", "skipped"):
                self.set_status("✔ Done - plug in the next phone", "ok")
                self.emit("beep", {"kind": "auto"})
            elif res:
                self.set_status("{name}: {detail}", "bad", name=res.name, detail=res.detail or "Failed")
                self.emit("beep", {"kind": "bad"})
            return
        failed = self._keys_with("failed")
        if self.settings.get("retry_once") and failed and not batch["retry"] and not batch.get("cancelled"):
            self.set_status("Trying the failed phones once more...")
            self.log(f"Auto retry: {len(failed)} phone(s)", "cmd")
            self.start_batch(failed, "normal", replace=True, retry=True)
            return
        self.manual_batch = None
        ok = sum(r.status == "success" for r in results)
        bad = sum(r.status in ("failed", "sig") for r in results)
        skip = sum(r.status in ("skipped", "older") for r in results)
        self.progress = {"done": self.progress["total"], "total": self.progress["total"], "running": False}
        self.set_status("{ok} success, {bad} failed, {skip} skipped", "ok" if bad == 0 else "bad", ok=ok, bad=bad, skip=skip)
        self.finish = {"n": self.finish["n"] + 1, "bad": bad}
        self.emit("beep", {"kind": "ok" if bad == 0 else "bad"})
        if self.settings.get("front_when_done"):
            self._bring_front()
        if self.settings.get("auto_csv") and results:
            try:
                folder = app_dir() / "reports"
                folder.mkdir(exist_ok=True)
                path = folder / f"apk-install-{datetime.now():%Y%m%d-%H%M%S}.csv"
                self._write_csv(str(path), results)
                self.log(f"CSV saved: {path}", "ok")
            except OSError:
                logging.exception("auto csv failed")
        self.dirty = True

    def _bring_front(self) -> None:
        try:
            self.window.restore()
            self.window.show()
            self.window.on_top = True
            threading.Timer(0.6, lambda: setattr(self.window, "on_top", False)).start()
        except Exception:
            logging.info("could not bring the window forward")

    def retry_failed(self) -> None:
        with self.lock:
            devs = self._keys_with("failed")
            if devs and self.manual_batch is None:
                self.start_batch(devs, "normal", replace=True)

    def retry_signature(self) -> None:
        with self.lock:
            devs = self._keys_with("sig")
            if devs and self.manual_batch is None:
                self.start_batch(devs, "uninstall_retry", targets={d.key: {self.pkg_of[d.key]} for d in devs if d.key in self.pkg_of})

    def retry_downgrade(self) -> None:
        with self.lock:
            devs = self._keys_with("older")
            if devs and self.manual_batch is None:
                self.start_batch(devs, "downgrade", targets={d.key: {self.pkg_of[d.key]} for d in devs if d.key in self.pkg_of})

    def _write_csv(self, path: str, rows: list[JobResult]) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Phone", "Connection", "Serial", "Old version", "New version", "Result", "Time"])
            for r in rows:
                w.writerow([r.name, r.conn, r.serial, r.old, r.new, f"{r.status} {r.detail}".strip(), r.when])

    def export_csv(self) -> None:
        if not self.history or self.window is None:
            self.toast("There are no results yet.", "bad")
            return
        kind = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
        path = self.window.create_file_dialog(kind, save_filename="apk-install-results.csv",
                                              file_types=("CSV (*.csv)",))
        if not path:
            return
        path = path if isinstance(path, str) else path[0]
        try:
            self._write_csv(path, self.history)
            self.toast("CSV saved: {path}", "ok", path=path)
        except OSError as exc:
            self.toast("Could not write the file: {err}", "bad", err=str(exc))

    def reset_handled(self) -> None:
        with self.lock:
            self.handled.clear()
            self.set_status("Auto-install list reset (all phones will count as new again).")

    # ---------- adb tools ----------
    def restart_adb(self) -> None:
        def work() -> None:
            self.adb.kill_server()
            self.adb.start_server()
            self.devman.refresh_now()

        self.bg(work, lambda _r: (self.set_status("ADB restarted."), self.toast("ADB restarted.", "ok")))

    def fix_problems(self) -> None:
        self.set_status("Finding and fixing problems...")

        def work() -> list[str]:
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
                    lines.append(f"• {p.get('name', '?')} ({p.get('addr')}): NOT_CONNECTED")
            return lines

        def done(lines: list[str]) -> None:
            self.set_status("Fix problems finished.")
            self.emit("alert", {"title": "Problem fix report", "body": "", "list": lines, "foot": "",
                                "empty": "All phones are fine ✔"})

        self.bg(work, done)

    # ---------- adb setup ----------
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
        self.dirty = True

        def startup() -> None:
            self.adb.start_server()
            self.devman.start()
            if self.settings.get("reconnect_saved"):
                self.devman.reconnect_saved()

        self.bg(startup)

    def download_adb(self) -> None:
        def done(path: str) -> None:
            if self._verify(path):
                self._enter_main(path)
            else:
                self.toast("Cannot run adb.exe. Choose another file with Browse adb.exe.", "bad")

        self.bg(lambda: AdbClient.download_platform_tools(lambda got, total: self.events.put(("dl", got, total))), done,
                lambda exc: self.toast("{err}", "bad", err=str(exc)))

    def browse_adb(self) -> None:
        if self.window is None:
            return
        kind = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
        path = self.window.create_file_dialog(kind, file_types=("adb (adb.exe)", "All files (*.*)"))
        if not path:
            return
        path = path if isinstance(path, str) else path[0]
        if self._verify(path):
            self._enter_main(path)
        else:
            self.toast("Could not run this file. Choose the correct adb.exe.", "bad")

    # ---------- Apps tab ----------
    def load_apps(self, key: str, scope: str) -> None:
        dev = next((d for d in self.devices if d.key == key and d.usable), None)
        if not dev:
            self.toast("No phone found. Add a phone first.", "bad")
            return
        name = dev.model or dev.serial
        self.set_status("{phone}: loading the app list...", phone=name)

        def done(pkgs: list[str]) -> None:
            self.set_status("{phone}: found {n} app(s).", phone=name, n=len(pkgs))
            self.emit("apps", {"key": key, "scope": scope, "pkgs": pkgs})
            self.toast("{n} apps loaded", n=len(pkgs))

        self.bg(lambda: self.adb.list_packages(dev.serial, scope), done)

    def app_action(self, key: str, scope: str, kind: str, pkgs: list[str]) -> None:
        dev = next((d for d in self.devices if d.key == key and d.usable), None)
        if not dev or not pkgs:
            return
        system = scope in ("system", "disabled")
        verb = "Uninstall" if kind == "uninstall" else "Clear data"

        def work() -> tuple[list[str], list[str]]:
            out, done = [], []
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

        def finished(result: tuple[list[str], list[str]]) -> None:
            lines, done = result
            for line in lines:
                self.log(line, "bad" if "Failed" in line else "ok")
            self.installed.clear()
            self.checking.clear()
            self._ensure_plans()
            bad = len(lines) - len(done)
            self.set_status("Done. {ok} succeeded, {bad} failed. Details are in the Log tab.", "bad" if bad else "info",
                            ok=len(done), bad=bad)
            self.emit("apps_done", {"removed": done if kind == "uninstall" else []})

        self.bg(work, finished)

    # ---------- Connection ----------
    def conn_task(self, which: str) -> None:
        fn = {"find": self.devman.find_phones, "saved": self.devman.reconnect_saved,
              "disconnect_all": lambda: self.devman.disconnect(None)}[which]
        self.toast({"find": "Searching", "saved": "Connecting", "disconnect_all": "Disconnecting"}[which])

        def done(res: Any) -> None:
            text = res[1] if isinstance(res, tuple) else str(res)
            self.log(text, "ok")
            self.emit("toast_raw", {"text": text.strip().splitlines()[0] if text.strip() else "", "kind": "ok"})

        self.bg(fn, done)

    def reconnect(self, addr: str) -> None:
        def done(res: Any) -> None:
            ok = self.adb.is_connected(res)
            if ok:
                self.toast("Phone connected", "ok")
            else:
                self.toast("Connect failed: {err}", "bad", err=res.text)
            self.devman.refresh_now()

        self.toast("Connecting")
        self.bg(lambda: self.adb.connect(addr), done)

    def disconnect(self, serial: str) -> None:
        self.bg(lambda: self.devman.disconnect([serial]),
                lambda r: self.emit("toast_raw", {"text": str(r).splitlines()[0] if str(r) else "", "kind": "info"}))

    def pair_qr(self) -> dict[str, Any]:
        try:
            image = self.pairing.start()
            buf = io.BytesIO()
            image.resize((240, 240)).save(buf, format="PNG")
            return {"ok": True, "img": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}
        except Exception as exc:
            return {"ok": False, "err": str(exc)}

    def pair_stop(self) -> None:
        self.pairing.stop()

    def pair(self, addr: str, code: str) -> None:
        def done(res: Any) -> None:
            self.emit("pair_result", {"ok": "Successfully paired" in res.text, "text": res.text})

        self.bg(lambda: self.adb.pair(addr.strip(), code.strip()), done)

    def connect(self, addr: str) -> None:
        def done(res: Any) -> None:
            self.emit("connect_result", {"ok": self.adb.is_connected(res), "text": res.text})
            self.devman.refresh_now()

        self.bg(lambda: self.adb.connect(addr.strip()), done)

    def tcp_start(self, key: str) -> None:
        dev = next((d for d in self.devices if d.key == key and d.usable and d.conn == "USB"), None)
        if not dev:
            self.emit("tcp_step", {"step": 0, "state": "fail", "msg": "Plug in a phone with a USB cable first."})
            return
        serial, adb = dev.serial, self.adb

        def step(i: int, state: str, msg: str = "", **params: Any) -> None:
            self.emit("tcp_step", {"step": i, "state": state, "msg": msg, "params": params})

        def work() -> None:
            step(1, "active")
            ip = adb.wifi_ip(serial)
            if not ip:
                step(1, "fail", "Could not read the phone's Wi-Fi address. Is the phone connected to Wi-Fi?")
                return
            step(1, "done")
            step(2, "active")
            res = adb.tcpip(serial, 5555)
            if not res.ok:
                step(2, "fail", "tcpip failed: {err}", err=res.text)
                return
            step(2, "done")
            step(3, "active")
            time.sleep(2)
            addr = f"{ip}:5555"
            for _ in range(3):
                if adb.is_connected(adb.connect(addr)):
                    step(3, "done")
                    step(4, "done", "Connected over Wi-Fi: {addr}. You can unplug the cable now.", addr=addr)
                    self.devman.refresh_now()
                    return
                time.sleep(1.5)
            step(3, "fail", "Could not connect to {addr}. Check that the PC and phone are on the same Wi-Fi.", addr=addr)

        self.bg(work)
