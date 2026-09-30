"""CryptAudio — application entry point (Phase 6).

Launches the Tkinter desktop GUI. Run from the project root with:

    .venv\\Scripts\\python.exe main.py

No backend logic lives here; this module only bootstraps the GUI, which in turn
delegates all real work to :mod:`services.cryptaudio_service`.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

# Ensure the project root is importable when run directly as a script.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from gui.main_window import MainWindow  # noqa: E402  (import after path setup)


def main() -> int:
    """Create the main window and start the Tkinter event loop."""
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # e.g. no display available
        print(f"Unable to start the CryptAudio GUI: {exc}", file=sys.stderr)
        return 1

    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
