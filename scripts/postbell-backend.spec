# PyInstaller spec for the Postbell FastAPI backend.
#
# Build with the wrapper at `postbell-electron/scripts/bundle-backend.py`,
# not by invoking pyinstaller directly, so paths stay consistent.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# This spec lives in postbellelectron/scripts/. Project root (which contains
# backend/ as a sibling of scripts/) is ONE level up. (Previously this was
# 2 up because backend/ lived in a sibling repo postbell2/; now self-contained.)
SPEC_PATH = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_PATH.parent

# Entry point: backend/__main__.py
ENTRY = str(PROJECT_ROOT / "backend" / "__main__.py")

# pathex must include the project root so `from backend.main import app` resolves.
PATHEX = [str(PROJECT_ROOT)]

# Hidden imports — modules that PyInstaller's static analysis misses because
# they are imported dynamically (uvicorn protocol auto-detection, SQLAlchemy
# dialect loading, etc.) or referenced via strings.
HIDDENIMPORTS = [
    # SQLAlchemy SQLite dialect (loaded by URL scheme, not import)
    "sqlalchemy.dialects.sqlite",
    # Uvicorn lifespan + protocol implementations
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    # tzdata package — required for `zoneinfo.ZoneInfo("America/Sao_Paulo")`
    # because Windows has no system tz database to fall back on.
    "tzdata",
    # Pull in every backend submodule so dynamically-registered models /
    # routers (e.g. `import backend.models  # noqa: F401`) survive bundling.
    *collect_submodules("backend"),
]

# Data files — googleapiclient ships a `discovery_cache/documents/*.json`
# directory that the YouTube client loads at runtime. google-auth has
# similar embedded assets (well-known certs).
DATAS = []
DATAS += collect_data_files("googleapiclient")
DATAS += collect_data_files("google_auth_oauthlib")
DATAS += collect_data_files("google.auth")
# tzdata ships its IANA tz database as package data (zoneinfo files).
DATAS += collect_data_files("tzdata")

block_cipher = None


a = Analysis(
    [ENTRY],
    pathex=PATHEX,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="postbell-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="postbell-backend",
)
