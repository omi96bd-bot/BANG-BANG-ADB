"""Settings stored in settings.json next to the app (or exe)."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any


def app_dir() -> Path:
    """Folder of the exe (when frozen) or of this source file."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class Settings:
    DEFAULTS: dict[str, Any] = {
        "adb_path": "",
        "last_apk_dir": "",
        "grant": True,
        "force": False,
        "workers": 5,
        "mode": "simple",
        "saved_phones": [],
        "geometry": "1020x760",
    }

    def __init__(self) -> None:
        self.path = app_dir() / "settings.json"
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {
            k: (list(v) if isinstance(v, list) else v) for k, v in self.DEFAULTS.items()
        }
        self.load()

    def load(self) -> None:
        """Read the file; a missing or corrupt file simply means defaults."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        with self._lock:
            for key, default in self.DEFAULTS.items():
                if key in raw and isinstance(raw[key], type(default)):
                    self.data[key] = raw[key]

    def save(self) -> None:
        with self._lock:
            text = json.dumps(self.data, indent=2, ensure_ascii=False)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # read-only folder: settings just won't persist

    def get(self, key: str) -> Any:
        with self._lock:
            return self.data[key]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.data[key] = value

    def saved_phones(self) -> list[dict[str, str]]:
        with self._lock:
            return [dict(p) for p in self.data["saved_phones"] if isinstance(p, dict)]

    def remember_phone(self, key: str, name: str, addr: str) -> bool:
        """Remember a Wi-Fi phone. Returns True if the file content changed."""
        with self._lock:
            phones = self.data["saved_phones"]
            for phone in phones:
                if isinstance(phone, dict) and phone.get("key") == key:
                    if phone.get("addr") == addr and phone.get("name") == name:
                        return False
                    phone.update(addr=addr, name=name)
                    break
            else:
                phones.append({"key": key, "name": name, "addr": addr})
        self.save()
        return True
