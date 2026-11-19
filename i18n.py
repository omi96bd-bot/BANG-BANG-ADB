"""Language support. T("English text") returns the Bangla text when the language is Bangla.
The English text itself is the key, so a missing translation simply shows English."""
from __future__ import annotations

_lang = "en"


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in ("en", "bn") else "en"


def get_lang() -> str:
    return _lang


def T(text: str, **kw: object) -> str:
    out = BN.get(text, text) if _lang == "bn" else text
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw) if "{" in text else text
    return out


BN: dict[str, str] = {
    "Waiting": "অপেক্ষায়", "Checking": "দেখা হচ্ছে", "Installing": "ইনস্টল হচ্ছে", "Success": "সফল", "Skipped": "বাদ",
    "Signature mismatch": "সিগনেচার মেলেনি", "APK older (Skipped)": "APK পুরোনো (বাদ)",
    # navigation and common
    "Install": "ইনস্টল", "Apps": "অ্যাপ", "Connection": "কানেকশন", "Log": "লগ", "Settings": "সেটিংস",
    "Theme": "থিম", "Light": "হালকা", "Dark": "গাঢ়", "Refresh": "রিফ্রেশ", "Add phone": "ফোন যোগ করুন",
    "Phones": "ফোন", "Phone": "ফোন", "All": "সব", "None": "কিছু না", "Select all": "সব সিলেক্ট",
    "Cancel": "বাতিল", "Copy": "কপি", "Copied": "কপি হয়েছে", "Confirm": "নিশ্চিত করুন", "Start": "শুরু",
    "Connect": "কানেক্ট", "Pair": "পেয়ার", "Disconnect": "ডিসকানেক্ট", "Reconnect": "আবার কানেক্ট",
    "Offline": "অফলাইন", "Failed": "ব্যর্থ", "Apps": "অ্যাপ",
    # install page
    "Install apps": "অ্যাপ ইনস্টল",
    "Drop an APK here, or click to choose one": "এখানে APK ফেলুন, অথবা ক্লিক করে বেছে নিন",
    "Click to choose an APK file": "ক্লিক করে APK ফাইল বেছে নিন",
    "Ctrl+O also opens the file chooser": "Ctrl+O চাপলেও ফাইল বাছাই খুলবে",
    "Drag and drop needs the tkinterdnd2 package": "টেনে এনে ফেলতে tkinterdnd2 প্যাকেজ লাগবে",
    "USB only": "শুধু USB", "Wi-Fi only": "শুধু Wi-Fi",
    "Phone (Model / Serial)": "ফোন (মডেল / সিরিয়াল)", "Installed version": "ইনস্টল করা ভার্সন",
    "Plan": "পরিকল্পনা", "Status": "অবস্থা", "Not installed": "ইনস্টল নেই",
    "Update (-r)": "আপডেট (-r)", "Reinstall (-r)": "আবার ইনস্টল (-r)", "Skip (same)": "বাদ (একই ভার্সন)",
    "APK older - skip": "APK পুরোনো - বাদ",
    "No phone yet. Add one to start.": "এখনও কোনো ফোন নেই। শুরু করতে একটা যোগ করুন।",
    "{done} / {total} done": "{done} / {total} শেষ",
    "Choose an APK, tick the phones, then press Install.": "একটা APK বেছে নিন, ফোন টিক দিন, তারপর ইনস্টল চাপুন।",
    "APK ready. Tick the phones and press Install.": "APK তৈরি। ফোন টিক দিয়ে ইনস্টল চাপুন।",
    "Reading APK...": "APK পড়া হচ্ছে...", "Choose an APK first.": "আগে একটা APK বেছে নিন।",
    "Tick at least one phone.": "অন্তত একটা ফোন টিক দিন।",
    "Installing... keep the phones unlocked.": "ইনস্টল হচ্ছে... ফোন আনলক রাখুন।",
    "Cancelling... running jobs will finish first.": "বাতিল হচ্ছে... চলমান কাজ আগে শেষ হবে।",
    "Trying the failed phones once more...": "ব্যর্থ ফোনগুলো আরেকবার চেষ্টা হচ্ছে...",
    "Auto retry: {n} phone(s)": "অটো রিট্রাই: {n}টি ফোন",
    "{ok} success, {bad} failed, {skip} skipped": "{ok}টি সফল, {bad}টি ব্যর্থ, {skip}টি বাদ",
    "Batch finished": "ব্যাচ শেষ", "Finished ✔": "শেষ ✔", "Finished with {n} problem(s)": "শেষ, {n}টি সমস্যা",
    "Installing...": "ইনস্টল হচ্ছে...", "Install log": "ইনস্টল লগ", "Full log": "পুরো লগ",
    "✔ Done - plug in the next phone": "✔ শেষ - পরের ফোন লাগান",
    "Copy error": "এরর কপি", "Retry failed": "ব্যর্থগুলো আবার", "Uninstall old and retry": "পুরোনোটা মুছে আবার ইনস্টল",
    "Try downgrade (-r -d)": "ডাউনগ্রেড চেষ্টা (-r -d)", "CSV Export": "CSV এক্সপোর্ট",
    "There are no results yet.": "এখনও কোনো ফলাফল নেই।", "CSV saved: {path}": "CSV সেভ হয়েছে: {path}",
    "Could not write the file: {err}": "ফাইল লেখা যায়নি: {err}",
    "Install options": "ইনস্টল অপশন", "Grant all permissions (-g)": "সব পারমিশন দিন (-g)",
    "Force reinstall": "জোর করে আবার ইনস্টল", "Auto-install on new phones": "নতুন ফোনে অটো ইনস্টল",
    "Open the app after install": "ইনস্টলের পর অ্যাপ খুলুন",
    "Phones at once (1-10):": "একসাথে কয়টা ফোন (১-১০):", "Phones at once (1-10)": "একসাথে কয়টা ফোন (১-১০)",
    "Command preview:": "কমান্ড প্রিভিউ:", "Restart ADB": "ADB রিস্টার্ট", "Fix problems": "সমস্যা ঠিক করুন",
    "Reset auto-install list": "অটো ইনস্টল তালিকা রিসেট",
    "Auto-install is on. From now on, every new phone you plug in will be installed.":
        "অটো ইনস্টল চালু। এখন থেকে প্রতিটা নতুন ফোন লাগালেই ইনস্টল হবে।",
    "Auto-install is on. Choose an APK first.": "অটো ইনস্টল চালু। আগে একটা APK বেছে নিন।",
    "Auto-install list reset (all phones will count as new again).": "অটো ইনস্টল তালিকা রিসেট হয়েছে (সব ফোন আবার নতুন ধরা হবে)।",
    "Refreshing phones...": "ফোন রিফ্রেশ হচ্ছে...",
    "Choose APK": "APK বাছুন", "This format cannot be installed directly": "এই ফরম্যাট সরাসরি ইনস্টল হয় না",
    "These files cannot be installed directly:": "এই ফাইলগুলো সরাসরি ইনস্টল হয় না:",
    "First extract them like a ZIP and give the .apk files inside.": "আগে ZIP-এর মতো এক্সট্র্যাক্ট করুন, তারপর ভেতরের .apk ফাইল দিন।",
    "Split APK?": "স্প্লিট APK?",
    "{pkg} has {n} files.\nAre these split APKs of the same app? (adb install-multiple will be used)":
        "{pkg}-এর {n}টি ফাইল আছে।\nএগুলো কি একই অ্যাপের স্প্লিট APK? (adb install-multiple ব্যবহার হবে)",
    "Could not read APK info (run pip install pyaxmlparser or keep aapt available). The package name will be asked at install time.":
        "APK-র তথ্য পড়া যায়নি (pip install pyaxmlparser চালান বা aapt রাখুন)। ইনস্টলের সময় প্যাকেজ নাম জিজ্ঞেস করা হবে।",
    "unknown package": "অজানা প্যাকেজ", "Package name": "প্যাকেজ নাম",
    "Enter the package name of {name} (for example com.example.app):": "{name}-এর প্যাকেজ নাম লিখুন (যেমন com.example.app):",
    "App: {pkgs}\nPhones:\n{names}\n\nThe old app will be uninstalled and the new one installed.\nWarning: all data of this app will be erased!\n\nContinue?":
        "অ্যাপ: {pkgs}\nফোন:\n{names}\n\nপুরোনো অ্যাপ মুছে নতুনটা ইনস্টল হবে।\nসতর্কতা: এই অ্যাপের সব ডেটা মুছে যাবে!\n\nচালিয়ে যাবেন?",
    "Downgrade": "ডাউনগ্রেড",
    "Phones:\n{names}\n\nWill try to install the older version with -r -d.\nNote: Android usually allows downgrade only for debuggable apps, so this may fail.\nThen you must Uninstall and install the older version, which erases the app data.\n\nTry it?":
        "ফোন:\n{names}\n\n-r -d দিয়ে পুরোনো ভার্সন ইনস্টলের চেষ্টা হবে।\nমনে রাখুন: Android সাধারণত শুধু debuggable অ্যাপে ডাউনগ্রেড দেয়, তাই এটা ব্যর্থ হতে পারে।\nতখন মুছে পুরোনো ভার্সন ইনস্টল করতে হবে, এতে অ্যাপের ডেটা মুছে যাবে।\n\nচেষ্টা করবেন?",
    "ADB restarted.": "ADB রিস্টার্ট হয়েছে।", "Finding and fixing problems...": "সমস্যা খুঁজে ঠিক করা হচ্ছে...",
    "Fix problems finished.": "সমস্যা ঠিক করা শেষ।", "Problem fix report": "সমস্যা সমাধানের রিপোর্ট",
    "All phones are fine ✔": "সব ফোন ঠিক আছে ✔",
    "not connected - Wireless debugging ON? Same Wi-Fi? AP isolation off on the router? If needed, pair again from Add phone.":
        "কানেক্টেড নয় - Wireless debugging চালু? একই Wi-Fi? রাউটারে AP isolation বন্ধ? দরকার হলে ফোন যোগ করুন থেকে আবার পেয়ার করুন।",
    "Error: {err}": "ত্রুটি: {err}",
    # apps page
    "Apps on phone": "ফোনের অ্যাপ", "Load apps": "অ্যাপ লোড", "User apps": "ইউজার অ্যাপ",
    "System apps": "সিস্টেম অ্যাপ", "Disabled": "বন্ধ করা", "Search:": "খুঁজুন:", "Uninstall": "আনইনস্টল",
    "Clear data": "ডেটা মুছুন", "Showing {a} / total {b}": "দেখাচ্ছে {a} / মোট {b}",
    "{phone}: loading the app list...": "{phone}: অ্যাপের তালিকা লোড হচ্ছে...",
    "{phone}: found {n} app(s).": "{phone}: {n}টি অ্যাপ পাওয়া গেছে।", "{n} apps loaded": "{n}টি অ্যাপ লোড হয়েছে",
    "No phone found. Add a phone first.": "কোনো ফোন পাওয়া যায়নি। আগে ফোন যোগ করুন।",
    "Load the apps first, then select one or more apps.": "আগে অ্যাপ লোড করুন, তারপর এক বা একাধিক অ্যাপ সিলেক্ট করুন।",
    "Warning: all data of the app will be erased!": "সতর্কতা: অ্যাপের সব ডেটা মুছে যাবে!",
    "Warning: these are system apps. Removing the wrong app can break calls, network or settings on the phone.\nThe app is removed for the current user only; a factory reset brings it back.":
        "সতর্কতা: এগুলো সিস্টেম অ্যাপ। ভুল অ্যাপ মুছলে ফোনের কল, নেটওয়ার্ক বা সেটিংস নষ্ট হতে পারে।\nঅ্যাপ শুধু বর্তমান ইউজারের জন্য মুছবে; ফ্যাক্টরি রিসেটে ফিরে আসবে।",
    "{verb} - {n} app(s)\nPhone: {phone} ({serial})\n\n{shown}\n\n{warn}\n\nContinue?":
        "{verb} - {n}টি অ্যাপ\nফোন: {phone} ({serial})\n\n{shown}\n\n{warn}\n\nচালিয়ে যাবেন?",
    "... and {n} more": "... আরও {n}টি",
    "Done. {ok} succeeded, {bad} failed. Details are in the Log tab.": "শেষ। {ok}টি সফল, {bad}টি ব্যর্থ। বিস্তারিত লগ ট্যাবে।",
    # log
    "Clear log": "লগ মুছুন", "Copy log": "লগ কপি",
    # settings
    "Look and sound": "চেহারা ও শব্দ", "Light or dark window": "হালকা বা গাঢ় উইন্ডো", "Language": "ভাষা",
    "English or Bangla. The window restarts its layout.": "English বা বাংলা। উইন্ডোর লেআউট নতুন করে সাজবে।",
    "Animations": "অ্যানিমেশন", "Turn off on a slow PC": "ধীর পিসিতে বন্ধ রাখুন",
    "Sound after each phone": "প্রতিটা ফোনের পর শব্দ", "A beep when a phone or a batch is done": "ফোন বা ব্যাচ শেষ হলে বিপ শব্দ",
    "Grant all permissions": "সব পারমিশন দিন", "Adds -g to the install command": "ইনস্টল কমান্ডে -g যোগ হয়",
    "Wake the screen first": "আগে স্ক্রিন জাগান", "Many phones refuse installs while the screen is locked": "স্ক্রিন লক থাকলে অনেক ফোন ইনস্টল নেয় না",
    "Keep the phone awake while plugged in": "প্লাগ ইন থাকলে ফোন জাগিয়ে রাখুন",
    "Stops the screen from sleeping during the install. Restored after the batch.": "ইনস্টলের সময় স্ক্রিন ঘুমাবে না। ব্যাচ শেষে আগের অবস্থায় ফিরবে।",
    "Skip the Play Protect scan for adb installs": "adb ইনস্টলে Play Protect স্ক্যান বাদ",
    "Removes the extra popup. Switched back on after the batch.": "বাড়তি পপআপ আসবে না। ব্যাচ শেষে আবার চালু হবে।",
    "Retry failed phones once": "ব্যর্থ ফোন একবার আবার চেষ্টা", "Automatic second try after a batch": "ব্যাচের পর নিজে থেকে দ্বিতীয়বার চেষ্টা",
    "Starts the app on the phone when the install succeeds": "ইনস্টল সফল হলে ফোনে অ্যাপ চালু হবে",
    "Install timeout (seconds)": "ইনস্টল টাইমআউট (সেকেন্ড)", "Stop one stuck install after this time": "এই সময় পর আটকে থাকা ইনস্টল থামবে",
    "Show a small log window while installing": "ইনস্টলের সময় ছোট লগ উইন্ডো দেখান",
    "Bring the window forward when a batch ends": "ব্যাচ শেষে উইন্ডো সামনে আনুন",
    "Save a CSV report after every batch": "প্রতি ব্যাচের পর CSV রিপোর্ট সেভ",
    "Saved in the reports folder next to the app": "অ্যাপের পাশের reports ফোল্ডারে সেভ হবে",
    "Phones and files": "ফোন ও ফাইল", "Reconnect saved Wi-Fi phones at start": "শুরুতে সেভ করা Wi-Fi ফোন আবার কানেক্ট",
    "Remember the last APK folder": "শেষ APK ফোল্ডার মনে রাখুন", "Ask before uninstalling apps": "আনইনস্টলের আগে জিজ্ঞেস করুন",
    "System apps always ask": "সিস্টেম অ্যাপে সবসময় জিজ্ঞেস করবে", "ADB path": "ADB পাথ", "not set": "ঠিক করা নেই",
    "Change adb.exe": "adb.exe বদলান",
    # setup
    "ADB not found": "ADB পাওয়া যায়নি", "ADB ready · {n} phones": "ADB প্রস্তুত · {n}টি ফোন",
    "Google's platform-tools (adb) is needed to install apps on phones. Press the button below to download it automatically (internet needed). Or, if you already have adb.exe, choose it.":
        "ফোনে অ্যাপ ইনস্টল করতে Google-এর platform-tools (adb) লাগে। নিচের বাটন চাপলে নিজে থেকে ডাউনলোড হবে (ইন্টারনেট লাগবে)। adb.exe আগে থেকে থাকলে সেটা বেছে নিন।",
    "Download ADB automatically": "ADB নিজে থেকে ডাউনলোড", "Browse adb.exe": "adb.exe বাছুন", "Choose adb.exe": "adb.exe বাছুন",
    "Downloading...": "ডাউনলোড হচ্ছে...", "Downloading: {got:.1f} / {total:.1f} MB": "ডাউনলোড: {got:.1f} / {total:.1f} MB",
    "Downloading: {got:.1f} MB": "ডাউনলোড: {got:.1f} MB",
    "Cannot run adb.exe. Choose another file with Browse adb.exe.": "adb.exe চালানো যাচ্ছে না। \"adb.exe বাছুন\" দিয়ে অন্য ফাইল বাছুন।",
    "Could not run this file. Choose the correct adb.exe.": "এই ফাইল চালানো যায়নি। সঠিক adb.exe বাছুন।",
    # connection page
    "USB cable": "USB তার", "Fastest and simplest": "সবচেয়ে দ্রুত ও সহজ", "QR code": "QR কোড",
    "Android 11+, same Wi-Fi": "Android 11+, একই Wi-Fi", "Pairing code": "পেয়ারিং কোড", "Wireless debugging": "ওয়্যারলেস ডিবাগিং",
    "USB → Wi-Fi": "USB → Wi-Fi", "Then unplug the cable": "তারপর তার খুলে ফেলুন",
    "Disconnect all": "সব ডিসকানেক্ট", "Reconnect saved phones": "সেভ করা ফোন আবার কানেক্ট", "Find phones": "ফোন খুঁজুন",
    "Disconnecting": "ডিসকানেক্ট হচ্ছে", "Connecting": "কানেক্ট হচ্ছে", "Searching": "খোঁজা হচ্ছে",
    "No phone is connected yet. Pick a way below.": "এখনও কোনো ফোন কানেক্টেড নয়। নিচ থেকে একটা উপায় বেছে নিন।",
    "Add a phone: pick a way": "ফোন যোগ করুন: একটা উপায় বেছে নিন",
    "Connected ✔": "কানেক্টেড ✔", "Phone connected": "ফোন কানেক্ট হয়েছে",
    "Connect with a USB cable": "USB তার দিয়ে কানেক্ট", "Each step turns green by itself when it is done.": "প্রতিটা ধাপ শেষ হলে নিজে থেকে সবুজ হবে।",
    "Turn on Developer options (Settings > About phone > tap Build number 7 times)": "Developer options চালু করুন (Settings > About phone > Build number-এ ৭ বার ট্যাপ)",
    "Turn ON USB debugging": "USB debugging চালু করুন", "Connect the phone to the PC with a cable": "তার দিয়ে ফোন পিসিতে লাগান",
    "Tap Allow on the phone screen": "ফোনের স্ক্রিনে Allow চাপুন", "Phone found": "ফোন পাওয়া গেছে", "Phone found ✔": "ফোন পাওয়া গেছে ✔",
    "Waiting for a phone... (checks every 3 seconds)": "ফোনের অপেক্ষা... (প্রতি ৩ সেকেন্ডে দেখা হয়)",
    "Waiting for the phone...": "ফোনের অপেক্ষা...",
    "Phone is offline - unplug and replug the cable, then press Fix problems": "ফোন অফলাইন - তার খুলে আবার লাগান, তারপর \"সমস্যা ঠিক করুন\" চাপুন",
    "Connect with a QR code (Wi-Fi)": "QR কোড দিয়ে কানেক্ট (Wi-Fi)",
    "The PC and the phone must be on the same Wi-Fi. Android 11 or newer.": "পিসি আর ফোন একই Wi-Fi-তে থাকতে হবে। Android 11 বা নতুন।",
    "Phone: Settings > Developer options > Wireless debugging > turn ON": "ফোন: Settings > Developer options > Wireless debugging > চালু করুন",
    "Tap \"Pair device with QR code\" on the phone": "ফোনে \"Pair device with QR code\" চাপুন",
    "Create the QR code here": "এখানে QR কোড তৈরি করুন", "Scan the QR code with the phone": "ফোন দিয়ে QR কোড স্ক্যান করুন",
    "Pairing and connecting": "পেয়ারিং ও কানেক্ট হচ্ছে", "Create QR code": "QR কোড তৈরি",
    "Waiting for the QR scan... (60 seconds)": "QR স্ক্যানের অপেক্ষা... (৬০ সেকেন্ড)",
    "To enable QR pairing, install: ": "QR পেয়ারিং চালু করতে ইনস্টল করুন: ",
    "Could not create the QR: {err}": "QR তৈরি করা যায়নি: {err}", "Use the pairing code method": "পেয়ারিং কোড পদ্ধতি ব্যবহার করুন",
    "Connect with a pairing code (Wi-Fi)": "পেয়ারিং কোড দিয়ে কানেক্ট (Wi-Fi)",
    "Phone: Wireless debugging > \"Pair device with pairing code\". Type the IP:PORT and the 6-digit code it shows.":
        "ফোন: Wireless debugging > \"Pair device with pairing code\"। সেখানে দেখানো IP:PORT আর ৬ সংখ্যার কোড লিখুন।",
    "Wireless debugging is ON (same Wi-Fi as this PC)": "Wireless debugging চালু (পিসির সাথে একই Wi-Fi)",
    "Tap \"Pair device with pairing code\"": "\"Pair device with pairing code\" চাপুন",
    "Pair: enter the IP:PORT and the 6-digit code": "পেয়ার: IP:PORT আর ৬ সংখ্যার কোড লিখুন",
    "Connect: enter the IP:PORT from the main Wireless debugging screen": "কানেক্ট: Wireless debugging-এর মূল স্ক্রিনের IP:PORT লিখুন",
    "Pair IP:PORT": "পেয়ার IP:PORT", "6-digit code": "৬ সংখ্যার কোড", "Connect IP:PORT": "কানেক্ট IP:PORT",
    "Enter both the IP:PORT and the code.": "IP:PORT আর কোড দুটোই লিখুন।", "Pairing...": "পেয়ার হচ্ছে...",
    "Pairing successful. Now enter the Connect IP:PORT and press Connect.": "পেয়ার সফল। এবার Connect IP:PORT লিখে কানেক্ট চাপুন।",
    "Pairing failed: {err}": "পেয়ার ব্যর্থ: {err}", "Enter the Connect IP:PORT.": "Connect IP:PORT লিখুন।",
    "Connecting...": "কানেক্ট হচ্ছে...", "Connect failed: {err}": "কানেক্ট ব্যর্থ: {err}",
    "Switch a USB phone to Wi-Fi": "USB ফোনকে Wi-Fi-তে নিন",
    "The phone must be plugged in with the cable and be on the same Wi-Fi as this PC.": "ফোন তারে লাগানো থাকতে হবে এবং পিসির সাথে একই Wi-Fi-তে থাকতে হবে।",
    "Keep the USB cable plugged in": "USB তার লাগানো রাখুন", "Read the phone's Wi-Fi address": "ফোনের Wi-Fi ঠিকানা পড়া",
    "Switch the phone to Wi-Fi mode (tcpip 5555)": "ফোনকে Wi-Fi মোডে নেওয়া (tcpip 5555)", "Connect over Wi-Fi": "Wi-Fi দিয়ে কানেক্ট",
    "You can unplug the cable now": "এখন তার খুলে ফেলতে পারেন", "Plug in a phone with a USB cable first.": "আগে USB তার দিয়ে একটা ফোন লাগান।",
    "Ready. Press Start.": "প্রস্তুত। শুরু চাপুন।", "Working...": "কাজ চলছে...",
    "Could not read the phone's Wi-Fi address. Is the phone connected to Wi-Fi?": "ফোনের Wi-Fi ঠিকানা পড়া যায়নি। ফোন কি Wi-Fi-তে আছে?",
    "tcpip failed: {err}": "tcpip ব্যর্থ: {err}",
    "Could not connect to {addr}. Check that the PC and phone are on the same Wi-Fi.": "{addr}-এ কানেক্ট করা যায়নি। পিসি আর ফোন একই Wi-Fi-তে আছে কিনা দেখুন।",
    "Connected over Wi-Fi: {addr}. You can unplug the cable now.": "Wi-Fi দিয়ে কানেক্ট হয়েছে: {addr}। এখন তার খুলতে পারেন।",
    # help window
    "Phone setup help": "ফোন সেটআপ সাহায্য", "Brand:": "ব্র্যান্ড:",
}
