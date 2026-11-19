# BANG BANG ADB (Windows)

Install Android apps (.apk) on one or many phones from a Windows PC, using ADB. USB cable and Wi-Fi.
One single window (no Simple/Advanced). English and বাংলা (Settings > Language). Light and dark theme.

The window is a web page (`web/index.html`) shown by **pywebview**, so the design is exactly the demo
(rounded cards, shadows, smooth animations). All logic is Python.

## Pages
| Page | What it does |
|---|---|
| Install | Choose/drop an APK, tick phones, Install. Refresh, live log popup, retry buttons, install options |
| Apps | Phone dropdown (USB or Wi-Fi), User/System/Disabled/All, search, Uninstall, Clear data |
| Connection | Connected/offline phones + USB, QR, pairing code, USB→Wi-Fi with live steps |
| Log | adb log |
| Settings | Theme, language, animations, sound, wake screen, keep awake, Play Protect skip, auto retry, timeout, ... |

## Files
| File | What it does |
|---|---|
| app.py | Start here. `python app.py` opens the window |
| core.py | All logic (phones, install, retry, apps, connect). No window code |
| web/index.html | The whole user interface (HTML + CSS + JavaScript) |
| i18n.py | Bangla texts. Add a new English text and its Bangla here |
| help_text.py | Phone-brand setup help (English + Bangla) |
| adb_client.py, devices.py, pairing.py, installer.py, settings.py | adb engine (unchanged) |

## Run from source
1. Install Python 3.11 or 3.12 for Windows (tick "Add to PATH").
2. `pip install -r requirements.txt`
3. `python app.py`

Needs Microsoft Edge WebView2 (already in Windows 10/11; otherwise install the "Evergreen runtime" from Microsoft).
If adb is not found, the app shows a button to download Google's platform-tools.
Drag and drop of APK files needs pywebview 5 or newer; the click-to-choose box always works.

## Build the exe
Run `build.bat`, or use the GitHub workflow (Actions > Build Windows exe > Run workflow).
`dist\BangBangADB.exe` is one file; adb and the page are packed inside. settings.json is saved next to the exe.

## How to use
1. Open **Connection** and follow the USB, QR or pairing-code steps.
2. Go to **Install**, drop an APK (or click the box).
3. Tick the phones, press **Install**.
