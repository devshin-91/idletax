"""Assembles the mobile prototype: the page, IdleTax's engine files and a Pyodide runtime in one folder.

Usage: python -X utf8 tools/build_mobile_proto.py <pyodide package folder> [out folder]
  <pyodide package folder>  the unpacked npm package pyodide@0.26.4 (the folder with pyodide.asm.wasm)
  [out folder]              default build/mobile-proto

The page runs the real core.py and i18n.py in the browser, so every number is the desktop app's own calculation.
page.html is the body-only page for publishing as a claude.ai Artifact; index.html wraps it for a local server.
"""
import base64
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tools", "mobile_proto")
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
WRAP = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "build", "mobile-proto")
    missing = [f for f in PYODIDE_FILES if not os.path.exists(os.path.join(src, f))]
    if missing:
        sys.exit("not found in " + src + ": " + ", ".join(missing))
    os.makedirs(os.path.join(out, "py"), exist_ok=True)
    os.makedirs(os.path.join(out, "pyodide"), exist_ok=True)
    for name, folder in (("core", ROOT), ("i18n", ROOT), ("bridge", HERE)):
        shutil.copyfile(os.path.join(folder, name + ".py"), os.path.join(out, "py", name + ".py.txt"))
    for f in PYODIDE_FILES:
        if f == "python_stdlib.zip":
            # claude.ai Artifacts do not serve .zip files, so the standard library ships as base64 text
            # and the page turns it back into bytes before Pyodide asks for it.
            with open(os.path.join(src, f), "rb") as fh, \
                    open(os.path.join(out, "pyodide", f + ".b64.txt"), "w", encoding="ascii") as dst:
                dst.write(base64.b64encode(fh.read()).decode("ascii"))
            continue
        shutil.copyfile(os.path.join(src, f), os.path.join(out, "pyodide", f))
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as fh:
        page = fh.read()
    with open(os.path.join(out, "page.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(WRAP + page + "\n</body></html>\n")
    print("built", out)


if __name__ == "__main__":
    main()
