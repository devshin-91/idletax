@echo off
rem Builds the single-file executable dist\IdleTax.exe. Tests run first, and the finished exe must pass a smoke test.
rem First time only: uv venv --python 3.14 .venv ^&^& uv pip install --python .venv\Scripts\python.exe pyinstaller
rem
rem The excluded modules are standard-library parts the app never uses. Remove an exclude only if the app
rem starts importing it, and update THIRD-PARTY-NOTICES.md at the same time.
cd /d "%~dp0"
.venv\Scripts\python.exe -X utf8 test_core.py || exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name IdleTax ^
  --exclude-module unittest --exclude-module pydoc ^
  --exclude-module ssl --exclude-module _ssl --exclude-module hashlib --exclude-module _hashlib ^
  --exclude-module socket --exclude-module _socket --exclude-module select ^
  --exclude-module bz2 --exclude-module _bz2 --exclude-module lzma --exclude-module _lzma ^
  --exclude-module compression.zstd --exclude-module _zstd ^
  --exclude-module decimal --exclude-module _decimal --exclude-module _pydecimal ^
  app.py || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke.ps1 || exit /b 1
echo Built dist\IdleTax.exe
