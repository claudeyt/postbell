"""Build the standalone Postbell backend executable with PyInstaller.

Usage (from anywhere):
    python postbell-electron/scripts/bundle-backend.py

Or via the npm script (run from postbell-electron/):
    npm run build:backend

Wipes prior build artifacts, invokes PyInstaller on the spec file, then
reports the resulting executable path and bundle size.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

# Resolve paths relative to this script: <root>/postbell-electron/scripts/bundle-backend.py
SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parent
ELECTRON_DIR = SCRIPTS_DIR.parent
PROJECT_ROOT = ELECTRON_DIR.parent

SPEC_FILE = SCRIPTS_DIR / "postbell-backend.spec"
DIST_DIR = ELECTRON_DIR / "dist-backend"
BUILD_DIR = ELECTRON_DIR / "build"
WORK_DIR = BUILD_DIR / "pyinstaller-work"

EXPECTED_EXE = DIST_DIR / "postbell-backend" / "postbell-backend.exe"


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or unit == "GiB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} GiB"


def _dir_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _clean() -> None:
    for target in (DIST_DIR, BUILD_DIR):
        if target.exists():
            print(f"[bundle-backend] cleaning {target}")
            shutil.rmtree(target, ignore_errors=True)


def main() -> int:
    if not SPEC_FILE.exists():
        print(f"[bundle-backend] ERROR: spec not found at {SPEC_FILE}", file=sys.stderr)
        return 2

    print(f"[bundle-backend] project root : {PROJECT_ROOT}")
    print(f"[bundle-backend] spec file    : {SPEC_FILE}")
    print(f"[bundle-backend] dist target  : {DIST_DIR}")

    _clean()

    try:
        import PyInstaller.__main__ as pyinst_main
    except ImportError as exc:
        print(
            "[bundle-backend] ERROR: PyInstaller is not installed in this "
            f"interpreter ({sys.executable}). Install dev deps first: "
            'pip install -e ".[dev]"',
            file=sys.stderr,
        )
        print(f"[bundle-backend] underlying error: {exc}", file=sys.stderr)
        return 3

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR),
    ]

    print(f"[bundle-backend] running: pyinstaller {' '.join(args)}")
    started = time.time()
    pyinst_main.run(args)
    elapsed = time.time() - started

    if not EXPECTED_EXE.exists():
        print(
            f"[bundle-backend] ERROR: build finished but exe not found at {EXPECTED_EXE}",
            file=sys.stderr,
        )
        return 4

    bundle_dir = EXPECTED_EXE.parent
    exe_size = EXPECTED_EXE.stat().st_size
    bundle_size = _dir_size(bundle_dir)

    print()
    print("[bundle-backend] BUILD OK")
    print(f"[bundle-backend]   duration   : {elapsed:.1f}s")
    print(f"[bundle-backend]   exe path   : {EXPECTED_EXE}")
    print(f"[bundle-backend]   exe size   : {_human_size(exe_size)}")
    print(f"[bundle-backend]   bundle dir : {bundle_dir}")
    print(f"[bundle-backend]   bundle size: {_human_size(bundle_size)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
