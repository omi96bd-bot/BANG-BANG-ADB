"""BANG BANG ADB entry point: python app.py  (window = pywebview, page = web/index.html)"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from settings import app_dir

EXPOSED = ("boot", "set_option", "refresh_all", "toggle_check", "select_all", "select_none", "raw_error", "pick_apks",
           "set_split", "set_package", "remove_apk", "install", "cancel", "retry_failed", "retry_signature",
           "retry_downgrade", "export_csv", "reset_handled", "restart_adb", "fix_problems", "download_adb",
           "browse_adb", "load_apps", "app_action", "conn_task", "reconnect", "disconnect", "pair_qr", "pair_stop",
           "pair", "connect", "tcp_start")


class Api:
    """The only object the web page can see (private attributes start with _ and stay hidden)."""

    def __init__(self, core: object) -> None:
        self._core = core


def _expose(name: str):
    def call(self, *args):
        return getattr(self._core, name)(*args)
    call.__name__ = name
    return call


for _n in EXPOSED:
    setattr(Api, _n, _expose(_n))


def resource(rel: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / rel


def main() -> None:
    try:
        logging.basicConfig(filename=str(app_dir() / "bangbangadb.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except OSError:
        pass
    logging.getLogger("pyaxmlparser").setLevel(logging.ERROR)
    try:
        import webview
        from core import Core

        core = Core()
        window = webview.create_window("BANG BANG ADB", url=resource("web/index.html").as_uri(), js_api=Api(core),
                                       width=1180, height=800, min_size=(980, 640), background_color="#eef2f6")
        core.attach(window)
        webview.start(core.start, debug=False)
    except Exception:
        logging.exception("fatal error")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "The app did not start. Details are in bangbangadb.log.\n"
                                                "Try: pip install pywebview", "BANG BANG ADB", 0x10)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
