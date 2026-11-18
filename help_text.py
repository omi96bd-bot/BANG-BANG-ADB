"""Phone setup help texts (Bengali) per brand."""
from __future__ import annotations

BRANDS: dict[str, tuple[str, list[str]]] = {
    "xiaomi": ("Xiaomi / POCO / Redmi", [
        "Settings > About phone: tap the MIUI/HyperOS version 7 times (Developer options turns on).",
        "Open Settings > Additional settings > Developer options.",
        "Turn ON \"USB debugging\".",
        "Turn ON \"Install via USB\" (needs Mi Account login and internet).",
        "Turn ON \"USB debugging (Security settings)\" (also needs Mi Account and internet).",
        "Keep the phone unlocked. When a popup appears during install, tap Allow / Install.",
    ]),
    "samsung": ("Samsung", [
        "Settings > About phone > Software information: tap Build number 7 times.",
        "Settings > Developer options: turn ON USB debugging.",
        "Keep USB mode as \"File transfer\" and tap Allow on the phone.",
        "If Auto Blocker is on (Settings > Security and privacy), turn it off for now; it can block USB installs.",
        "Keep the phone unlocked during install; if Play Protect or a security popup appears, tap Install anyway / Allow.",
    ]),
    "oppo": ("Oppo / Vivo / Realme", [
        "Settings > About phone: tap Build/Version number 7 times.",
        "Settings > Additional settings > Developer options: turn ON USB debugging.",
        "In Developer options, turn ON \"Install via USB\" or a similar option if present.",
        "If a security/Play Protect popup appears on the phone, tap Allow / Install; keep the phone unlocked.",
        "If the install gets stuck, temporarily turn off \"app install protection\" in the Security app.",
    ]),
    "infinix": ("Infinix / Tecno", [
        "Settings > About phone: tap Build number 7 times.",
        "Settings > Developer options: turn ON USB debugging.",
        "Keep USB mode as \"File transfer (MTP)\"; tap Allow on the phone.",
        "Tap Allow / Install on the popup during install; keep the phone unlocked.",
        "If Phone Master / the Security app blocks the install, turn it off temporarily.",
    ]),
    "generic": ("Other Android (Generic)", [
        "Settings > About phone: tap Build number 7 times.",
        "Open Developer options and turn ON USB debugging.",
        "Plug in the cable, keep USB mode as \"File transfer\", and tap Allow on the phone screen.",
        "Keep the phone unlocked during install and tap Allow / Install on any popup.",
        "When finished, turn off USB debugging / Wireless debugging.",
    ]),
}


def brand_key(manufacturer: str) -> str:
    m = manufacturer.lower()
    if any(w in m for w in ("xiaomi", "poco", "redmi")):
        return "xiaomi"
    if "samsung" in m:
        return "samsung"
    if any(w in m for w in ("oppo", "vivo", "realme")):
        return "oppo"
    if any(w in m for w in ("infinix", "tecno", "itel")):
        return "infinix"
    return "generic"
