# Third-party notices

StallMeter's own code uses only the Python standard library. `dist\StallMeter.exe` is built with PyInstaller and
therefore bundles the following third-party software.

| Component | What it is | License |
|---|---|---|
| CPython 3.14 (interpreter and the standard-library modules the app imports) | Runs the app | Python Software Foundation License Version 2 — https://docs.python.org/3/license.html |
| Tcl/Tk (bundled with CPython's `tkinter`) | Draws the window | Tcl/Tk License (BSD-style) — https://www.tcl-lang.org/software/tcltk/license.html |
| PyInstaller bootloader | Starts the bundled app | GPL-2.0-or-later with a special exception that allows distributing the built executable under any license — https://pyinstaller.org/en/stable/license.html |
| Microsoft Visual C++ runtime files shipped with CPython | Runtime support | Microsoft Visual Studio redistributable terms — see CPython's license page above |

Modules excluded from the build (see `build.bat`), and so not bundled: `ssl` (OpenSSL), `hashlib`, `socket`, `select`,
`bz2`, `lzma`, `compression.zstd`, `decimal`, `unittest`, `pydoc`.

If `build.bat` stops excluding one of these, add its license here.

## Mobile prototype (`tools/build_mobile_proto.py`)

The mobile screen prototype is not part of `StallMeter.exe`. Its build folder, and a page published from it,
contain these unmodified files from the npm package `pyodide@0.26.4`: `pyodide.js`, `pyodide.asm.js`,
`pyodide.asm.wasm`, `pyodide-lock.json` and `python_stdlib.zip` (stored as base64 text).

| Component | What it is | License |
|---|---|---|
| Pyodide 0.26.4 | Runs Python (and StallMeter's `core.py`) in the browser | Mozilla Public License 2.0 — https://github.com/pyodide/pyodide/blob/0.26.4/LICENSE (the npm `package.json` declares Apache-2.0) |
| CPython 3.12 and its standard library, compiled into Pyodide | The Python interpreter | Python Software Foundation License Version 2 — https://docs.python.org/3/license.html |
| Noto Sans KR (loaded from Google Fonts, not bundled) | Font | SIL Open Font License 1.1 |
