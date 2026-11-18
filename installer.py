"""Installer: APK reading, version plans, Bengali error help, parallel install jobs."""
from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from adb_client import CREATE_NO_WINDOW, AdbClient
from devices import Device
from settings import app_dir

INSTALL_TIMEOUT = 120


def _to_int(value: object) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- APK info
@dataclass
class ApkInfo:
    path: str
    package: Optional[str] = None
    version_name: Optional[str] = None
    version_code: Optional[int] = None

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class ApkGroup:
    """One install unit: a single APK, or several split APKs of one app."""
    apks: list[ApkInfo]
    split: bool = False

    @property
    def base(self) -> ApkInfo:
        for apk in self.apks:
            if "split" not in apk.name.lower() and "config." not in apk.name.lower():
                return apk
        return self.apks[0]

    @property
    def package(self) -> Optional[str]:
        return self.base.package

    @property
    def version_code(self) -> Optional[int]:
        return self.base.version_code

    @property
    def paths(self) -> list[str]:
        return [a.path for a in self.apks]


class ApkReader:
    """pyaxmlparser first, then aapt. Returns empty fields if neither works."""

    def __init__(self) -> None:
        local = app_dir() / "aapt.exe"
        self.aapt = shutil.which("aapt") or shutil.which("aapt2") or (str(local) if local.is_file() else None)

    def read(self, path: str) -> ApkInfo:
        info = ApkInfo(path=path)
        try:
            from pyaxmlparser import APK  # optional dependency

            apk = APK(path)
            info.package = apk.package or None
            info.version_name = str(apk.version_name) if apk.version_name else None
            info.version_code = _to_int(apk.version_code)
            if info.package:
                return info
        except Exception:
            pass
        if self.aapt:
            try:
                proc = subprocess.run(
                    [self.aapt, "dump", "badging", path],
                    capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                )
                text = proc.stdout.decode("utf-8", errors="replace")
                m = re.search(r"package: name='([^']+)'(?: versionCode='(\d+)')?(?: versionName='([^']*)')?", text)
                if m:
                    info.package = m.group(1)
                    info.version_code = _to_int(m.group(2))
                    info.version_name = m.group(3) or None
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass
        return info


# ---------------------------------------------------------------- error help
@dataclass
class ErrorInfo:
    code: str
    hint: str
    status: str = "failed"        # "failed" or "sig"
    brand_help: bool = False
    offer: str = ""               # "retry_r" | "uninstall" | "downgrade"
    package: str = ""


def explain_error(text: str, conn: str, package: str = "") -> ErrorInfo:
    """Turn raw adb/pm error text into a plain-language Bengali hint."""
    low = text.lower()
    if "INSTALL_FAILED_USER_RESTRICTED" in text:
        return ErrorInfo(
            "INSTALL_FAILED_USER_RESTRICTED",
            "In Developer options, turn ON Install via USB and USB debugging (Security settings); "
            "tap Allow on the phone screen during install and keep the phone unlocked.",
            brand_help=True,
        )
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in text:
        m = re.search(r"[Pp]ackage\s+([A-Za-z][\w.]+)\s+signatures", text)
        pkg = m.group(1) if m else package
        return ErrorInfo(
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
            "Signature mismatch. The old app must be removed and the new one installed (app data will be erased).",
            status="sig", offer="uninstall", package=pkg,
        )
    if "INSTALL_FAILED_ALREADY_EXISTS" in text:
        return ErrorInfo("INSTALL_FAILED_ALREADY_EXISTS",
                         "The app is already installed. Retry with -r (press Retry failed).", offer="retry_r")
    if "INSTALL_FAILED_VERSION_DOWNGRADE" in text:
        return ErrorInfo(
            "INSTALL_FAILED_VERSION_DOWNGRADE",
            "The phone has a newer version. You can try -r -d; if that also fails, uninstall first and install the older "
            "version, which erases the app data.",
            offer="downgrade", package=package,
        )
    if "INSTALL_FAILED_INSUFFICIENT_STORAGE" in text:
        return ErrorInfo("INSTALL_FAILED_INSUFFICIENT_STORAGE", "Not enough storage on the phone. Delete some files or apps to free space.")
    if "INSTALL_FAILED_OLDER_SDK" in text:
        return ErrorInfo("INSTALL_FAILED_OLDER_SDK", "This APK does not run on the phone's Android version (the phone's Android is too old).")
    if "INSTALL_FAILED_NO_MATCHING_ABIS" in text:
        return ErrorInfo("INSTALL_FAILED_NO_MATCHING_ABIS", "This APK does not support the phone's CPU (ABI).")
    if "unauthorized" in low:
        return ErrorInfo("UNAUTHORIZED", _connection_hint(conn))
    if any(s in low for s in ("device offline", "no devices/emulators", "not found", "cannot connect", "closed", "more than one device")):
        return ErrorInfo("OFFLINE", _connection_hint(conn))
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown error")
    return ErrorInfo("UNKNOWN", f"Unknown error: {first[:120]} (press Copy to copy the full error)")


def _connection_hint(conn: str) -> str:
    if conn == "Wi-Fi":
        return ("Check that the phone and PC are on the same Wi-Fi; turn off AP/Client isolation on the router; "
                "keep Wireless debugging ON; if needed, pair again from Add phone.")
    return ("Plug the cable in properly; keep USB mode as \"File transfer\"; tap Allow on the phone screen; "
            "otherwise unplug and replug the cable or press Fix problems.")


# ---------------------------------------------------------------- jobs
@dataclass
class JobOptions:
    grant: bool = True
    force: bool = False
    workers: int = 5
    replace_override: bool = False                      # retry with -r
    targets: dict[str, set[str]] = field(default_factory=dict)   # key -> packages (retry modes)


@dataclass
class JobResult:
    key: str
    serial: str
    name: str
    conn: str
    manufacturer: str = ""
    old: str = ""
    new: str = ""
    status: str = "waiting"     # success | failed | skipped | sig | older
    detail: str = ""
    raw: str = ""
    package: str = ""
    offer: str = ""
    brand_help: bool = False
    when: str = ""


def fmt_version(value: object) -> str:
    if isinstance(value, tuple):
        return f"{value[1]} ({value[0]})"
    return "" if value is None else str(value)


class Installer:
    """Runs installs on many phones in parallel and reports through the event queue."""

    def __init__(self, adb: AdbClient, events: queue.Queue) -> None:
        self.adb = adb
        self.events = events
        self._cancel: dict[int, threading.Event] = {}

    # ---------- planning ----------
    @staticmethod
    def plan(group: ApkGroup, installed: Optional[tuple[int, str]], force: bool) -> tuple[str, str]:
        """(action code, label). Compares integer versionCode only."""
        if installed is None:
            return "install", "Install"
        code = group.version_code
        if code is None:
            return "update", "Update (-r)"
        if code > installed[0]:
            return "update", "Update (-r)"
        if code == installed[0]:
            return ("reinstall", "Reinstall (-r)") if force else ("skip", "Skip (same)")
        return "older", "APK older - skip"

    def check_plans(self, gen: int, devices: list[Device], group: ApkGroup) -> None:
        """Read the installed version on each phone (background) and report it."""
        if not group.package:
            return
        package = group.package

        def one(dev: Device) -> None:
            try:
                value: object = self.adb.installed_version(dev.serial, package)
            except RuntimeError:
                value = "err"
            self.events.put(("inst", gen, dev.key, value))

        def run() -> None:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(one, devices))

        threading.Thread(target=run, daemon=True).start()

    # ---------- batches ----------
    def cancel(self, batch: int) -> None:
        ev = self._cancel.get(batch)
        if ev:
            ev.set()

    def start(self, batch: int, devices: list[Device], groups: list[ApkGroup],
              opts: JobOptions, mode: str = "normal") -> None:
        """mode: normal | uninstall_retry | downgrade"""
        self._cancel[batch] = threading.Event()
        threading.Thread(target=self._run_batch, args=(batch, devices, groups, opts, mode), daemon=True).start()

    def _run_batch(self, batch: int, devices: list[Device], groups: list[ApkGroup],
                   opts: JobOptions, mode: str) -> None:
        total, done = len(devices), 0
        workers = max(1, min(10, opts.workers))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self._job, batch, d, groups, opts, mode) for d in devices]
            for fut in as_completed(futures):
                done += 1
                self.events.put(("row", batch, fut.result()))
                self.events.put(("progress", batch, done, total))
        self._cancel.pop(batch, None)
        self.events.put(("batch_done", batch))

    def _state(self, batch: int, key: str, status: str, detail: str = "") -> None:
        self.events.put(("row_state", batch, key, status, detail))

    def _log(self, text: str, tag: str) -> None:
        self.events.put(("log", text, tag))

    def _job(self, batch: int, dev: Device, groups: list[ApkGroup], opts: JobOptions, mode: str) -> JobResult:
        res = JobResult(dev.key, dev.serial, dev.model, dev.conn, dev.manufacturer)
        try:
            self._job_body(batch, dev, groups, opts, mode, res)
        except Exception as exc:       # one phone must never break the batch
            res.status, res.detail, res.raw = "failed", f"Internal error: {exc}", str(exc)
        res.when = time.strftime("%Y-%m-%d %H:%M:%S")
        return res

    def _job_body(self, batch: int, dev: Device, groups: list[ApkGroup], opts: JobOptions,
                  mode: str, res: JobResult) -> None:
        cancel = self._cancel.get(batch) or threading.Event()
        if cancel.is_set():
            res.status, res.detail = "skipped", "Cancelled"
            return
        self._state(batch, dev.key, "checking")
        wanted = opts.targets.get(dev.key)
        outcomes: list[str] = []
        for index, group in enumerate(groups):
            if cancel.is_set():
                outcomes.append("skipped")
                res.detail = "Cancelled"
                break
            pkg = group.package or ""
            if mode != "normal" and wanted is not None and pkg not in wanted:
                continue
            try:
                installed = self.adb.installed_version(dev.serial, pkg) if pkg else None
            except RuntimeError as exc:
                self._fail(res, explain_error(str(exc), dev.conn, pkg), str(exc))
                outcomes.append("failed")
                break
            if index == 0:
                res.old = fmt_version(installed)
            action, _label = self.plan(group, installed, opts.force)
            if not pkg:
                action = "update"               # package unknown: cannot compare, just replace
            if mode == "uninstall_retry" and pkg:
                self._state(batch, dev.key, "installing", "Removing the old app...")
                un = self.adb.uninstall(dev.serial, pkg)
                self._log(f"{dev.model}: uninstall {pkg}: {un.text or un.code}", "ok" if un.ok else "bad")
                action = "install"
            downgrade = mode == "downgrade" and action == "older"
            if action == "skip":
                outcomes.append("skipped")
                res.detail = "Same version already installed"
                continue
            if action == "older" and not downgrade:
                outcomes.append("older")
                res.package = pkg
                res.detail = "APK version is older than the phone's - skipped"
                continue
            replace = downgrade or action in ("update", "reinstall") or opts.replace_override
            self._state(batch, dev.key, "installing")
            out = self.adb.install(dev.serial, group.paths, opts.grant, replace, downgrade, INSTALL_TIMEOUT)
            text = out.text
            if out.timed_out:
                res.detail = f"Timeout ({INSTALL_TIMEOUT}s) - check for a popup on the phone"
                res.raw = "timeout"
                outcomes.append("failed")
            elif "Success" in out.out:
                outcomes.append("success")
                try:
                    now = self.adb.installed_version(dev.serial, pkg) if pkg else None
                except RuntimeError:
                    now = None
                if index == 0 or not res.new:
                    res.new = fmt_version(now)
            else:
                info = explain_error(text, dev.conn, pkg)
                if info.code in ("OFFLINE", "UNAUTHORIZED"):
                    res.detail = "Failed (offline): " + info.hint
                    res.raw = text
                    outcomes.append("failed")
                else:
                    self._fail(res, info, text)
                    outcomes.append(info.status)
        res.status = self._summarise(outcomes)
        if res.status == "success":
            res.detail = ""
        elif res.status == "skipped" and not res.detail:
            res.detail = "Nothing to do"

    @staticmethod
    def _fail(res: JobResult, info: ErrorInfo, raw: str) -> None:
        res.detail, res.raw = info.hint, raw
        res.offer, res.brand_help = info.offer, info.brand_help
        if info.package:
            res.package = info.package

    @staticmethod
    def _summarise(outcomes: list[str]) -> str:
        for status in ("failed", "sig", "older", "success"):
            if status in outcomes:
                return status
        return "skipped"
