"""Entry point for the bundled Postbell backend.

Used by PyInstaller to produce a standalone executable. Kept intentionally
thin: imports the FastAPI `app` from `backend.main`, reads the port from the
`POSTBELL_PORT` environment variable (default 8001), and runs uvicorn.
"""

import os

import uvicorn

from backend.main import app


def main() -> None:
    port_raw = os.environ.get("POSTBELL_PORT", "8001")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8001
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
