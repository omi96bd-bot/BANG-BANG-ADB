"""DeviceManager: USB + Wi-Fi discovery, merging, saved phones, mDNS and subnet scan."""
from __future__ import annotations

import ipaddress
import queue
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from adb_client import AdbClient
from settings import Settings

POLL_SECONDS = 3

REASONS = {
    "unauthorized": "Tap Allow on the phone screen",
    "offline": "Offline - unplug and replug the cable, or press Fix problems",
    "no permissions": "USB driver/permission problem - try another cable/port, or install the phone's USB driver",
    "authorizing": "Checking permission... please wait",
    "connecting": "Connecting... please wait",
}


def is_wifi(serial: str) -> bool:
    """Wi-Fi phones have ip:port serials or mDNS style adb-XXXX serials."""
    return ":" in serial or serial.startswith("adb-")


@dataclass
class Device:
    serial: str                 # serial passed to `adb -s` (USB preferred)
    state: str
    model: str
    conn: str                   # "USB" or "Wi-Fi"
    key: str                    # real hardware serial if known, else serial
    manufacturer: str = ""
    alts: list[str] = field(default_factory=list)   # same phone, other transports
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.state == "device"


class DeviceManager:
    SCAN_PORT = 5555

    def __init__(self, adb: AdbClient, settings: Settings, events: queue.Queue) -> None:
        self.adb = adb
        self.settings = settings
        self.events = events
        self._info: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._adb_error_sent = False

    # ---------- polling ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                devs = self.refresh()
                if devs is None:
                    if not self._adb_error_sent:
                        self._adb_error_sent = True
                        self.events.put(("adb_error", "adb is not responding. Try Advanced > Restart ADB."))
                else:
                    self._adb_error_sent = False
                    self.events.put(("devices", devs))
            except Exception as exc:  # the poller must never die
                self.events.put(("log", f"Device poll error: {exc}", "bad"))
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def refresh(self) -> Optional[list[Device]]:
        """One poll: list phones, read their identity once, merge USB + Wi-Fi."""
        with self._lock:
            raw = self.adb.devices()
            if raw is None:
                return None
            current = {r["serial"] for r in raw}
            self._info = {s: v for s, v in self._info.items() if s in current}
            merged: dict[str, Device] = {}
            for r in raw:
                serial, state = r["serial"], r["state"]
                info = self._identity(serial) if state == "device" else {}
                key = info.get("real") or serial
                dev = Device(
                    serial=serial,
                    state=state,
                    model=info.get("model") or r["model"] or serial,
                    conn="Wi-Fi" if is_wifi(serial) else "USB",
                    key=key,
                    manufacturer=info.get("brand", ""),
                    reason="" if state == "device" else REASONS.get(state, f"Phone is in '{state}' state"),
                )
                old = merged.get(key)
                if old is None:
                    merged[key] = dev
                elif dev.conn == "USB" and old.conn == "Wi-Fi":   # prefer USB
                    dev.alts = old.alts + [old.serial]
                    merged[key] = dev
                else:
                    old.alts.append(dev.serial)
            devices = sorted(merged.values(), key=lambda d: (d.conn != "USB", d.model.lower()))
            for dev in devices:
                self._remember(dev)
            return devices

    def _identity(self, serial: str) -> dict[str, str]:
        if serial in self._info:
            return self._info[serial]
        props = self.adb.getprops(serial)
        if not props:
            return {}
        info = {
            "real": props.get("ro.serialno", ""),
            "model": props.get("ro.product.model", ""),
            "brand": props.get("ro.product.manufacturer", ""),
        }
        self._info[serial] = info
        return info

    def _remember(self, dev: Device) -> None:
        """Save Wi-Fi phones that have a plain ip:port address."""
        if not dev.usable:
            return
        for serial in [dev.serial] + dev.alts:      # a USB row can also hold a Wi-Fi transport
            if is_wifi(serial) and not serial.startswith("adb-"):
                self.settings.remember_phone(dev.key, dev.model, serial)

    # ---------- connecting ----------
    def _connect(self, addr: str) -> bool:
        return self.adb.is_connected(self.adb.connect(addr))

    def discover_mdns(self) -> list[str]:
        """Connect to every phone that advertises a Wireless-debugging connect service."""
        done = []
        for _name, stype, addr in self.adb.mdns_services():
            if stype.startswith("_adb-tls-connect") and self._connect(addr):
                done.append(addr)
        return done

    def reconnect_saved(self) -> str:
        """Try saved addresses, then mDNS (Wireless-debugging ports change)."""
        ok = []
        for phone in self.settings.saved_phones():
            addr = phone.get("addr", "")
            if addr and self._connect(addr):
                ok.append(addr)
        ok += [a for a in self.discover_mdns() if a not in ok]
        self.refresh_now()
        return f"{len(ok)} phone(s) connected." + ("\n" + "\n".join(ok) if ok else "")

    @staticmethod
    def _local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))   # private target: no packet is sent
                return s.getsockname()[0]
        except OSError:
            return socket.gethostbyname(socket.gethostname())

    def local_hosts(self) -> list[str]:
        """All other hosts of this PC's own private /24. Never a public range."""
        ip = self._local_ip()
        if not ipaddress.ip_address(ip).is_private:
            raise ValueError("This PC is not on a private network; scan skipped.")
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
        return [str(h) for h in net.hosts() if str(h) != ip]

    @staticmethod
    def _port_open(host: str, port: int = 5555, timeout: float = 0.3) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0

    def scan_subnet(self) -> list[str]:
        hosts = self.local_hosts()
        with ThreadPoolExecutor(max_workers=64) as pool:
            flags = list(pool.map(self._port_open, hosts))
        return [h for h, ok in zip(hosts, flags) if ok]

    def find_phones(self) -> str:
        """mDNS + port 5555 scan, then adb connect on every hit."""
        found = self.discover_mdns()
        note = ""
        try:
            for host in self.scan_subnet():
                addr = f"{host}:{self.SCAN_PORT}"
                if addr not in found and self._connect(addr):
                    found.append(addr)
        except (ValueError, OSError) as exc:
            note = f"\n(Subnet scan did not run: {exc})"
        self.refresh_now()
        if not found:
            return ("No phone found. Same Wi-Fi? Wireless debugging ON? AP isolation off on the router?" + note)
        return f"{len(found)} phone(s) found:\n" + "\n".join(found) + note

    def switch_to_wifi(self, serial: str) -> tuple[bool, str]:
        """USB phone -> Wi-Fi on fixed port 5555. IP is read before tcpip restarts the transport."""
        ip = self.adb.wifi_ip(serial)
        if not ip:
            return False, "Could not read the phone's Wi-Fi IP. Check that the phone is connected to Wi-Fi."
        res = self.adb.tcpip(serial, self.SCAN_PORT)
        if not res.ok:
            return False, f"tcpip failed: {res.text}"
        time.sleep(2)
        addr = f"{ip}:{self.SCAN_PORT}"
        for _ in range(3):
            if self._connect(addr):
                self.refresh_now()
                return True, (f"Connected over Wi-Fi: {addr}\nYou can unplug the cable now.\n"
                              "Note: port 5555 is fixed; it stops working after a phone reboot, then repeat this step over USB.")
            time.sleep(1.5)
        return False, f"Could not connect to {addr}. Check that the PC and phone are on the same Wi-Fi."

    def disconnect(self, serials: Optional[list[str]]) -> str:
        """serials=None disconnects everything."""
        if serials is None:
            res = self.adb.disconnect()
            self.refresh_now()
            return res.text or "All Wi-Fi connections were disconnected."
        lines = [self.adb.disconnect(s).text for s in serials]
        self.refresh_now()
        return "\n".join(lines) or "No Wi-Fi phone was selected."
