"""
Development preview launcher.

Serves the real application (web UI + REST API + HID supervisor) on 0.0.0.0 so it
can be opened from another device or from a hosted preview environment.

Usage:
    python app/web/preview_server.py [porta]
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.main import main  # noqa: E402


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            port = 8080
    port = int(os.environ.get("PORT", port))
    sys.exit(main(["--host", "0.0.0.0", "--port", str(port), "--no-browser"]))
