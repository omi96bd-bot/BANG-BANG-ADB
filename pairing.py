"""PairingService: QR pairing for Android 11+ using mDNS (zeroconf) + `adb pair`."""
from __future__ import annotations

import importlib.util
import queue
import secrets
import string
import threading
import time
from typing import Any, Optional

from adb_client import AdbClient

PAIR_TYPE = "_adb-tls-pairing._tcp.local."
CONNECT_TYPE = "_adb-tls-connect._tcp.local."
TIMEOUT_SECONDS = 60


class PairingService:
    """Secrets live only in memory for one session and are wiped by stop()."""

    def __init__(self, adb: AdbClient, events: queue.Queue) -> None:
        self.adb = adb
        self.events = events
        self._lock = threading.Lock()
        self._session = 0
        self._name = ""
        self._password = ""
        self._zc: Any = None
        self._browsers: list[Any] = []
        self._connect_ports: dict[str, int] = {}
        self._pair_started = False
        self._finished = False

    @staticmethod
    def missing_packages() -> list[str]:
        needed = (("zeroconf", "zeroconf"), ("qrcode", "qrcode"), ("PIL", "pillow"))
        return [pip for module, pip in needed if importlib.util.find_spec(module) is None]

    # ---------- public ----------
    def start(self) -> Any:
        """Begin a session. Returns a PIL image of the QR code."""
        import qrcode  # optional dependency

        self.stop()
        alphabet = string.ascii_letters + string.digits
        with self._lock:
            self._session += 1
            sid = self._session
            self._name = "studio-" + "".join(secrets.choice(alphabet) for _ in range(8))
            self._password = "".join(secrets.choice(alphabet) for _ in range(10))
            payload = f"WIFI:T:ADB;S:{self._name};P:{self._password};;"
            self._connect_ports = {}
            self._pair_started = False
            self._finished = False
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")
        threading.Thread(target=self._listen, args=(sid,), daemon=True).start()
        threading.Thread(target=self._watchdog, args=(sid,), daemon=True).start()
        return image

    def stop(self) -> None:
        """End the session and throw the random name/password away."""
        with self._lock:
            self._session += 1
            self._name = ""
            self._password = ""
            zc, self._zc = self._zc, None
            self._browsers = []
        if zc is not None:
            try:
                zc.close()
            except Exception:
                pass

    # ---------- internals ----------
    def _emit(self, sid: int, kind: str, text: str) -> None:
        """kind: status | ok | fail | timeout. ok/fail/timeout are sent only once."""
        with self._lock:
            if sid != self._session:
                return
            if kind != "status":
                if self._finished:
                    return
                self._finished = True
        self.events.put(("pair", kind, text))

    def _listen(self, sid: int) -> None:
        try:
            from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

            zc = Zeroconf()
        except Exception as exc:
            self._emit(sid, "fail", f"Could not start mDNS: {exc}")
            return
        with self._lock:
            if sid != self._session:
                zc.close()
                return
            self._zc = zc

        def handler(zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
            if state_change != ServiceStateChange.Removed:
                threading.Thread(target=self._resolve, args=(sid, zeroconf, service_type, name), daemon=True).start()

        try:
            self._browsers = [ServiceBrowser(zc, t, handlers=[handler]) for t in (PAIR_TYPE, CONNECT_TYPE)]
        except Exception as exc:
            self._emit(sid, "fail", f"Could not start the mDNS browser: {exc}")

    def _watchdog(self, sid: int) -> None:
        end = time.time() + TIMEOUT_SECONDS
        while time.time() < end:
            with self._lock:
                if sid != self._session or self._finished or self._pair_started:
                    return
            time.sleep(0.5)
        self._emit(sid, "timeout", "No phone found within 60 seconds. Same Wi-Fi? Wireless debugging ON? AP isolation off on the router?")

    def _resolve(self, sid: int, zc: Any, service_type: str, name: str) -> None:
        try:
            info = zc.get_service_info(service_type, name, timeout=3000)
        except Exception:
            return
        if info is None:
            return
        ips = [a for a in info.parsed_addresses() if ":" not in a]
        if not ips:
            return
        ip, port = ips[0], info.port
        suffix = "." + service_type
        instance = name[: -len(suffix)] if name.endswith(suffix) else name.split(".")[0]
        if service_type == CONNECT_TYPE:
            with self._lock:
                if sid == self._session:
                    self._connect_ports[ip] = port
            return
        with self._lock:
            if sid != self._session or instance != self._name or self._pair_started:
                return
            self._pair_started = True
            password = self._password
        self._emit(sid, "status", "Phone found, pairing...")
        res = self.adb.pair(f"{ip}:{port}", password)
        with self._lock:
            self._password = ""        # one use only
        if "Successfully paired" not in res.text:
            self._emit(sid, "fail", f"Pair failed: {res.text or 'No reply'}")
            return
        self._emit(sid, "status", "Pairing successful. Looking for the connection...")
        self._connect_phase(sid, ip)

    def _connect_phase(self, sid: int, ip: str) -> None:
        deadline = time.time() + 25
        while time.time() < deadline:
            with self._lock:
                if sid != self._session:
                    return
                port: Optional[int] = self._connect_ports.get(ip)
            if port is None:
                for _name, _type, addr in self.adb.mdns_services():
                    if addr.startswith(ip + ":"):
                        port = int(addr.rsplit(":", 1)[1])
                        break
            if port is not None:
                res = self.adb.connect(f"{ip}:{port}")
                if self.adb.is_connected(res):
                    self._emit(sid, "ok", f"Connected: {ip}:{port}")
                    return
            time.sleep(2)
        self._emit(sid, "fail", "Paired, but the connect service was not found. Connect using the IP:PORT shown on the Wireless debugging page.")
