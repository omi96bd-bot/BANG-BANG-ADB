"""BANG BANG ADB entry point: python app.py"""
from __future__ import annotations

import logging
import sys

from settings import app_dir


def main() -> None:
    try:
        logging.basicConfig(filename=str(app_dir() / "bangbangadb.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except OSError:
        pass                                   # read-only folder: skip the log file
    logging.getLogger("pyaxmlparser").setLevel(logging.ERROR)
    try:
        from ui import App
        App().run()
    except Exception:
        logging.exception("fatal error")
        try:
            from tkinter import messagebox
            messagebox.showerror("BANG BANG ADB", "The app did not start. Details are in bangbangadb.log.")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
