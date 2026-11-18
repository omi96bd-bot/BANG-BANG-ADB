# BANG BANG ADB (Windows)

Install Android apps (.apk) on one or many phones from a Windows PC, using ADB.
Works over USB cable and over Wi-Fi. Has a **Simple** mode and an **Advanced** mode.

## Files
| File | What it does |
|---|---|
| app.py | Start here. Run `python app.py` |
| ui.py | The window (Tkinter) |
| wizard.py | "Add phone" wizard (USB / QR / pairing code) and brand help window |
| adb_client.py | All adb calls and output parsing, adb download |
| devices.py | Finds USB + Wi-Fi phones, merges duplicates, saved phones, scan |
| pairing.py | QR pairing (mDNS) |
| installer.py | APK info, version check, error help, parallel installs |
| settings.py, help_text.py | Settings file and English help texts |

Apps tab (Advanced mode): pick any connected phone, choose User/System/Disabled/All apps, search, multi-select and Uninstall or Clear data. System apps are removed with `pm uninstall --user 0` (current user only).
| requirements.txt, build.bat, .github/workflows/build.yml | Build helpers |

## Run from source
1. Install Python 3.10+ for Windows (tick "Add to PATH").
2. `pip install -r requirements.txt` (all packages are optional except pyinstaller for building)
3. `python app.py`

If adb is not found, the app shows a button to download Google's platform-tools for you.

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
1. Press **Add phone** and follow USB, QR or pairing code steps.
2. Drop an APK on the window (or click the blue box).
3. Tick the phones, press **Install**.
Advanced mode adds options, command preview, Apps tab, Wireless tab, Log, CSV export, Auto-install.

Auto-install: when switched on, only phones that appear AFTER that are installed automatically.
Use "Auto list reset" to make all connected phones count as new again.

## 8 manual tests
1. One USB phone: plug in, tap Allow, install an APK, see Success.
2. One Wi-Fi phone via QR code (Android 11+, same Wi-Fi).
3. One Wi-Fi phone via pairing code + connect IP:PORT.
4. A USB phone moved to Wi-Fi with "Switch USB phone to Wi-Fi", then unplug the cable.
5. USB and Wi-Fi phones together; the same phone on both shows as ONE row (USB).
6. A phone that has an older version: plan shows "Update (-r)", result shows the new version.
7. A phone with a different signature: row shows "Signature mismatch", then "Uninstall old and retry" (one warning).
8. Auto-install ON with three phones plugged in one after another: each gets the green "Done - next phone" message and a beep.

## Known limits (honest list)
- The code was written and its logic (adb output parsing, merging, version plans, install jobs, error hints) was
  tested only on Linux with a fake adb script. It was NOT run on Windows, with real phones, or with the real
  Tkinter window (Tkinter was not available where it was written). Expect small fixes on first run.
- QR pairing and mDNS (zeroconf) were not tested with a real phone. Firewalls, VPNs and routers with AP isolation can block it.
- Two-line cells (model + serial) in the table rely on Tk showing line breaks; if your Tk does not, the cell shows one line.
- Switch USB to Wi-Fi reads the phone's IP first and then runs `tcpip 5555` (safer order than the reverse).
- .apks / .xapk / .aab bundles are not supported; extract them first.
- Downgrade (-r -d) usually fails on release apps; Android allows it mainly for debuggable apps.
- If neither pyaxmlparser nor aapt is available, the app cannot read APK info and asks you to type the package name (no version compare then).
- Brand help steps are general; menu names change between phone software versions.
- Some antivirus programs warn about PyInstaller one-file exes. Building yourself on GitHub is the safest.
