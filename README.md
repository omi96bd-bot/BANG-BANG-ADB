# BANG BANG ADB (Windows)

Install Android apps (.apk) on one or many phones from a Windows PC, using ADB.
Works over USB cable and over Wi-Fi. One single window: **no Simple/Advanced split any more**.
Languages: **English and বাংলা** (Settings > Language).

## Pages (left sidebar)
| Page | What it does |
|---|---|
| Install | Choose APK, tick phones, press Install. Install options are folded under the list. Refresh button, live log popup, retry buttons |
| Apps | Choose a phone in the dropdown (USB or Wi-Fi), load User/System/Disabled/All apps, search, Uninstall or Clear data |
| Connection | Shows every phone (connected or offline). Pick USB / QR / pairing code / USB→Wi-Fi and follow the live steps |
| Log | Full adb log with Copy and Clear |
| Settings | Theme, language, animations, sound and all the install options below |

## Settings
Light/Dark theme, English/বাংলা, animations on/off, sound, grant permissions, wake the screen first,
keep the phone awake (restored after), skip the Play Protect scan (restored after), retry failed phones once,
open the app after install, install timeout, phones at once, small log popup, bring window forward when done,
CSV report after every batch, reconnect saved Wi-Fi phones at start, remember last APK folder, confirm before uninstall.

## Files
| File | What it does |
|---|---|
| app.py | Start here. Run `python app.py` |
| ui.py | The window: sidebar, Install/Apps/Log/Settings pages, install logic |
| connection.py | Connection page (phone status + step-by-step connect flows) |
| widgets.py | Colours (light/dark), buttons, toggle, progress bar, toast, animations |
| i18n.py | Bangla translations (`T("English text")`). Add new texts here |
| help_window.py, help_text.py | Brand setup help (English and Bangla) |
| adb_client.py, devices.py, pairing.py, installer.py | adb calls, phone discovery, QR pairing, installs (unchanged engine) |
| settings.py | Settings file |
| requirements.txt, build.bat, .github/workflows/build.yml | Build helpers |

Texts that come from adb itself or from the install engine (for example some error explanations) stay in English.

## Run from source
1. Install Python 3.10+ for Windows (tick "Add to PATH").
2. `pip install -r requirements.txt` (all packages are optional except pyinstaller for building)
3. `python app.py`

If adb is not found, the app shows a button to download Google's platform-tools for you.
Use a font with Bangla support (Windows has Nirmala UI by default).

## Build the exe on GitHub (no Python needed on your PC)
1. Create a new GitHub repository and upload all these files (keep the `.github` folder).
2. Open the **Actions** tab, choose **Build Windows exe**, press **Run workflow**.
3. When it is green, open the run and download **BangBangADB-windows** (a zip with one file: BangBangADB.exe, adb is packed inside).
4. Unzip anywhere and run BangBangADB.exe. On first start the packed adb is copied to `%LOCALAPPDATA%\BangBangADB\platform-tools`.

## Build the exe on your own PC
Run `build.bat`. It downloads platform-tools once (into `platform-tools/`) and packs it into the exe:

    pyinstaller --onefile --noconsole --name BangBangADB --add-data "platform-tools;platform-tools" --collect-all tkinterdnd2 --collect-all pyaxmlparser --collect-all zeroconf --collect-all qrcode app.py

`dist\BangBangADB.exe` is then a single file. adb search order: `platform-tools` folder next to the exe, adb packed inside the exe, PATH, saved path.
If you build without `--add-data`, put the `platform-tools` folder next to the exe (or press "Download ADB automatically").
settings.json is saved next to the exe, so use a folder you can write to.

## How to use
1. Open **Connection** and follow the USB, QR or pairing-code steps (the page shows when the phone is connected).
2. Go to **Install**, drop an APK on the window (or click the box).
3. Tick the phones, press **Install**. A small log window shows what is happening.

Auto-install: when switched on (Install options), only phones that appear AFTER that are installed automatically.
