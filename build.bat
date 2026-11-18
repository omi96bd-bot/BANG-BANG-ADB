@echo off
REM Build BangBangADB.exe on Windows (run inside the project folder). adb is packed INSIDE the exe.
pip install -r requirements.txt
if not exist platform-tools (
  powershell -NoProfile -Command "Invoke-WebRequest https://dl.google.com/android/repository/platform-tools-latest-windows.zip -OutFile pt.zip; Expand-Archive pt.zip -DestinationPath ."
  del pt.zip
)
pyinstaller --onefile --noconsole --name BangBangADB --add-data "platform-tools;platform-tools" --collect-all tkinterdnd2 --collect-all pyaxmlparser --collect-all zeroconf --collect-all qrcode app.py
echo.
echo Done. dist\BangBangADB.exe is a single file with adb inside. No other folder is needed.
pause
