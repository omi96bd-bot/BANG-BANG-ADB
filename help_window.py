"""Phone setup help popup (brand steps in English or Bangla)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from help_text import BRANDS, BRANDS_BN
from i18n import T, get_lang
from widgets import FONT, P

if TYPE_CHECKING:
    from ui import App


def show_brand_help(app: "App", brand: str) -> None:
    win = tk.Toplevel(app.root)
    win.title(T("Phone setup help"))
    win.geometry("580x440")
    win.configure(bg=P["bg"])
    win.transient(app.root)
    names = {k: v[0] for k, v in BRANDS.items()}
    chosen = tk.StringVar(value=names.get(brand, names["generic"]))
    top = tk.Frame(win, bg=P["bg"], padx=12, pady=10)
    top.pack(fill="x")
    tk.Label(top, text=T("Brand:"), font=(FONT, 10, "bold"), bg=P["bg"], fg=P["ink"]).pack(side="left")
    combo = ttk.Combobox(top, values=list(names.values()), textvariable=chosen, state="readonly", width=32)
    combo.pack(side="left", padx=8)
    body = tk.Text(win, wrap="word", font=(FONT, 11), padx=14, pady=10, relief="flat", bg=P["panel"], fg=P["ink"])
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def fill(*_: Any) -> None:
        key = next((k for k, v in names.items() if v == chosen.get()), "generic")
        steps = BRANDS_BN[key] if get_lang() == "bn" else BRANDS[key][1]
        body.config(state="normal")
        body.delete("1.0", "end")
        for i, step in enumerate(steps, 1):
            body.insert("end", f"{i}. {step}\n\n")
        body.config(state="disabled")

    combo.bind("<<ComboboxSelected>>", fill)
    fill()
