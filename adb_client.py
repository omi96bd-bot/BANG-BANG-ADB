"""AdbClient: every adb call and every piece of adb output parsing lives here."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from settings import app_dir

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
LogFn = Callable[[str, str], None]

_DEVICE_RE = re.compile(
    r"^(\S+)\s+(device|unauthorized|offline|no permissions|authorizing|recovery|"
    r"sideload|bootloader|connecting)\b(.*)$"
)
_PROP_RE = re.compile(r"^\[(.+?)\]: \[(.*)\]$")
_MDNS_RE = re.compile(r"^(\S+)\s+(_adb[\w-]*\._tcp)\.?\s+(\d+\.\d+\.\d+\.\d+:\d+)")


@dataclass
class AdbResult:
    code: int
    out: str
    err: str
    timed_out: bool = False

    @property
    def text(self) -> str:
        return "\n".join(p for p in (self.out.strip(), self.err.strip()) if p)

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out


class AdbClient:
    def __init__(self, path: Optional[str], log: Optional[LogFn] = None) -> None:
        self.path = path
        self.log: LogFn = log or (lambda msg, tag: None)

    # ---------- locating / downloading adb ----------
    @staticmethod
    def bundled_adb() -> Optional[str]:
        """adb packed inside the exe (PyInstaller --add-data). It is copied once to a normal folder,
        because adb keeps running in the background and must not live in the temporary unpack folder."""
        src = Path(getattr(sys, "_MEIPASS", "")) / "platform-tools"
        if not (src / "adb.exe").is_file():
            return None
        base = Path(os.environ.get("LOCALAPPDATA") or app_dir())
        dest = base / "BangBangADB" / "platform-tools"
        if not (dest / "adb.exe").is_file():
            try:
                shutil.copytree(src, dest, dirs_exist_ok=True)
            except OSError:
                return None
        return str(dest / "adb.exe") if (dest / "adb.exe").is_file() else None

    @staticmethod
    def find_adb(saved: str = "") -> Optional[str]:
        """platform-tools next to the app, then adb packed inside the exe, then PATH, then the saved path."""
        local = app_dir() / "platform-tools" / "adb.exe"
        if local.is_file():
            return str(local)
        packed = AdbClient.bundled_adb()
        if packed:
            return packed
        found = shutil.which("adb")
        if found:
            return found
        if saved and Path(saved).is_file():
            return saved
        return None

    @staticmethod
    def download_platform_tools(progress: Callable[[int, int], None]) -> str:
        """Download and extract platform-tools next to the app. Returns adb.exe path."""
        dest = app_dir()
        tmp = dest / "platform-tools.zip.part"
        try:
            with urllib.request.urlopen(PLATFORM_TOOLS_URL, timeout=20) as resp, open(tmp, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    progress(got, total)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Download failed. Check that the internet is working. ({exc})") from exc
        try:
            with zipfile.ZipFile(tmp) as zf:
                root = dest.resolve()
                for member in zf.infolist():  # block "zip slip" paths
                    target = (dest / member.filename).resolve()
                    if target != root and root not in target.parents:
                        raise RuntimeError("The ZIP file is not safe. Cancelled.")
                zf.extractall(dest)
        except (zipfile.BadZipFile, OSError) as exc:
            raise RuntimeError(f"Could not open the ZIP: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)
        adb = dest / "platform-tools" / "adb.exe"
        if not adb.is_file():
            raise RuntimeError("adb.exe was not found inside platform-tools.")
        return str(adb)

    # ---------- low level ----------
    def run(
        self,
        args: list[str],
        timeout: float = 30,
        serial: Optional[str] = None,
        shown: Optional[str] = None,
        quiet: bool = False,
    ) -> AdbResult:
        """Run adb with an argument list (never a shell string)."""
        cmd = [self.path or "adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += [str(a) for a in args]
        if not quiet:
            self.log("> " + (shown or "adb " + subprocess.list2cmdline(cmd[1:])), "cmd")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
            )
            return AdbResult(
                proc.returncode,
                proc.stdout.decode("utf-8", errors="replace"),
                proc.stderr.decode("utf-8", errors="replace"),
            )
        except subprocess.TimeoutExpired:
            return AdbResult(-1, "", "timeout", True)
        except (OSError, ValueError) as exc:
            return AdbResult(-2, "", str(exc))

    @staticmethod
    def is_connected(res: AdbResult) -> bool:
        t = res.text.lower()
        return res.ok and ("connected to" in t or "already connected" in t) and "cannot" not in t and "failed" not in t

    # ---------- server ----------
    def version(self) -> AdbResult:
        return self.run(["version"], timeout=10)

    def start_server(self) -> None:
        """Output goes to DEVNULL so the daemon cannot keep our pipes open."""
        self.log("> adb start-server", "cmd")
        try:
            subprocess.run(
                [self.path or "adb", "start-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass

    def kill_server(self) -> AdbResult:
        return self.run(["kill-server"], timeout=15)

    # ---------- devices ----------
    def devices(self) -> Optional[list[dict[str, str]]]:
        """Parse `adb devices -l`. None means adb itself failed."""
        res = self.run(["devices", "-l"], timeout=15, quiet=True)
        if not res.ok:
            return None
        found: list[dict[str, str]] = []
        for line in res.out.splitlines():
            m = _DEVICE_RE.match(line.strip())
            if not m:
                continue
            model = re.search(r"model:(\S+)", m.group(3))
            found.append(
                {
                    "serial": m.group(1),
                    "state": m.group(2),
                    "model": model.group(1).replace("_", " ") if model else "",
                }
            )
        return found

    def getprops(self, serial: str) -> dict[str, str]:
        res = self.run(["shell", "getprop"], timeout=15, serial=serial, quiet=True)
        props: dict[str, str] = {}
        for line in res.out.splitlines():
            m = _PROP_RE.match(line.strip())
            if m:
                props[m.group(1)] = m.group(2)
        return props

    # ---------- apps ----------
    def installed_version(self, serial: str, package: str) -> Optional[tuple[int, str]]:
        """(versionCode, versionName) or None if not installed. Raises RuntimeError if adb fails."""
        res = self.run(["shell", "dumpsys", "package", package], timeout=30, serial=serial)
        if not res.ok:
            raise RuntimeError(res.text or "adb error")
        if "Unable to find package" in res.out:
            return None
        code = re.search(r"versionCode=(\d+)", res.out)
        if not code:
            return None
        name = re.search(r"versionName=(\S+)", res.out)
        return int(code.group(1)), (name.group(1) if name else "?")

    @staticmethod
    def install_args(paths: list[str], grant: bool, replace: bool, downgrade: bool) -> list[str]:
        cmd = ["install-multiple" if len(paths) > 1 else "install"]
        if replace:
            cmd.append("-r")
        if downgrade:
            cmd.append("-d")
        if grant:
            cmd.append("-g")
        return cmd + list(paths)

    def install(self, serial: str, paths: list[str], grant: bool, replace: bool,
                downgrade: bool, timeout: float = 120) -> AdbResult:
        return self.run(self.install_args(paths, grant, replace, downgrade), timeout=timeout, serial=serial)

    def preview(self, serial: str, paths: list[str], grant: bool, replace: bool, downgrade: bool) -> str:
        args = ["adb", "-s", serial] + self.install_args(paths, grant, replace, downgrade)
        return subprocess.list2cmdline(args)

    def uninstall(self, serial: str, package: str) -> AdbResult:
        return self.run(["uninstall", package], timeout=60, serial=serial)

    def clear_data(self, serial: str, package: str) -> AdbResult:
        return self.run(["shell", "pm", "clear", package], timeout=60, serial=serial)

    def list_third_party(self, serial: str) -> list[str]:
        return self.list_packages(serial, "user")

    def list_packages(self, serial: str, scope: str = "user") -> list[str]:
        """scope: user (installed by you), system (built-in), disabled, all."""
        flag = {"user": ["-3"], "system": ["-s"], "disabled": ["-d"]}.get(scope, [])
        res = self.run(["shell", "pm", "list", "packages"] + flag, timeout=30, serial=serial)
        return sorted(line.strip()[8:] for line in res.out.splitlines() if line.strip().startswith("package:"))

    def uninstall_user0(self, serial: str, package: str) -> AdbResult:
        """Remove a built-in app for the current user only (no root needed; factory reset brings it back)."""
        return self.run(["shell", "pm", "uninstall", "--user", "0", package], timeout=60, serial=serial)

    # ---------- wireless ----------
    def pair(self, addr: str, code: str) -> AdbResult:
        return self.run(["pair", addr, code], timeout=30, shown=f"adb pair {addr} ******")

    def connect(self, addr: str) -> AdbResult:
        return self.run(["connect", addr], timeout=12)

    def disconnect(self, addr: Optional[str] = None) -> AdbResult:
        return self.run(["disconnect"] + ([addr] if addr else []), timeout=15)

    def mdns_services(self) -> list[tuple[str, str, str]]:
        """(instance name, service type, ip:port) from `adb mdns services`."""
        res = self.run(["mdns", "services"], timeout=15)
        found = []
        for line in res.out.splitlines():
            m = _MDNS_RE.match(line.strip())
            if m:
                found.append((m.group(1), m.group(2), m.group(3)))
        return found

    def tcpip(self, serial: str, port: int = 5555) -> AdbResult:
        return self.run(["tcpip", str(port)], timeout=15, serial=serial)

    def wifi_ip(self, serial: str) -> Optional[str]:
        res = self.run(["shell", "ip", "route"], timeout=10, serial=serial)
        for line in res.out.splitlines():
            m = re.search(r"dev wlan\d+\b.*\bsrc (\d+\.\d+\.\d+\.\d+)", line)
            if m:
                return m.group(1)
        res = self.run(["shell", "ip", "addr", "show", "wlan0"], timeout=10, serial=serial)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", res.out)
        return m.group(1) if m else None
