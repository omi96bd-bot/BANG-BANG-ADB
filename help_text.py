"""Phone setup help texts per brand (English and Bangla)."""
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

BRANDS_BN: dict[str, list[str]] = {
    "xiaomi": [
        "Settings > About phone: MIUI/HyperOS ভার্সনে ৭ বার ট্যাপ করুন (Developer options চালু হবে)।",
        "Settings > Additional settings > Developer options খুলুন।",
        "\"USB debugging\" চালু করুন।",
        "\"Install via USB\" চালু করুন (Mi Account লগইন ও ইন্টারনেট লাগবে)।",
        "\"USB debugging (Security settings)\" চালু করুন (এতেও Mi Account ও ইন্টারনেট লাগবে)।",
        "ফোন আনলক রাখুন। ইনস্টলের সময় পপআপ এলে Allow / Install চাপুন।",
    ],
    "samsung": [
        "Settings > About phone > Software information: Build number-এ ৭ বার ট্যাপ করুন।",
        "Settings > Developer options: USB debugging চালু করুন।",
        "USB মোড \"File transfer\" রাখুন এবং ফোনে Allow চাপুন।",
        "Auto Blocker চালু থাকলে (Settings > Security and privacy) আপাতত বন্ধ করুন, এটা USB ইনস্টল আটকাতে পারে।",
        "ইনস্টলের সময় ফোন আনলক রাখুন। Play Protect বা সিকিউরিটি পপআপ এলে Install anyway / Allow চাপুন।",
    ],
    "oppo": [
        "Settings > About phone: Build/Version number-এ ৭ বার ট্যাপ করুন।",
        "Settings > Additional settings > Developer options: USB debugging চালু করুন।",
        "Developer options-এ \"Install via USB\" বা এরকম কিছু থাকলে চালু করুন।",
        "ফোনে সিকিউরিটি/Play Protect পপআপ এলে Allow / Install চাপুন। ফোন আনলক রাখুন।",
        "ইনস্টল আটকে গেলে Security অ্যাপে \"app install protection\" সাময়িক বন্ধ করুন।",
    ],
    "infinix": [
        "Settings > About phone: Build number-এ ৭ বার ট্যাপ করুন।",
        "Settings > Developer options: USB debugging চালু করুন।",
        "USB মোড \"File transfer (MTP)\" রাখুন এবং ফোনে Allow চাপুন।",
        "ইনস্টলের সময় পপআপে Allow / Install চাপুন। ফোন আনলক রাখুন।",
        "Phone Master / Security অ্যাপ ইনস্টল আটকালে সাময়িক বন্ধ করুন।",
    ],
    "generic": [
        "Settings > About phone: Build number-এ ৭ বার ট্যাপ করুন।",
        "Developer options খুলে USB debugging চালু করুন।",
        "তার লাগান, USB মোড \"File transfer\" রাখুন এবং ফোনের স্ক্রিনে Allow চাপুন।",
        "ইনস্টলের সময় ফোন আনলক রাখুন এবং যেকোনো পপআপে Allow / Install চাপুন।",
        "কাজ শেষে USB debugging / Wireless debugging বন্ধ করে দিন।",
    ],
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
