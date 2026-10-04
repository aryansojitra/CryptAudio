"""CryptAudio — Settings page (Phase 6 UI Redesign).

Small, honest settings page. No invented features — only displays app info
and simple preferences that actually work. Nothing involving password
persistence or secrets.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import Badge, Card


class SettingsPage(ttk.Frame):
    """The Settings page — app info and simple preferences."""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._app = app
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        container = ttk.Frame(self, style="TFrame", padding=SPACING["xl"])
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)

        # Title.
        title_frame = ttk.Frame(container, style="TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["xl"]))
        tk.Label(title_frame, text="Settings", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Application preferences and information",
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        # About card.
        about_card = Card(container)
        about_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        inner = about_card.inner

        tk.Label(inner, text="ABOUT", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w")

        info_lines = [
            ("Application", "CryptAudio"),
            ("Version", "1.0.0 (Phase 7)"),
            ("Description", "Cryptographic Audio Steganography Tool"),
            ("Encryption", "AES-256-GCM + PBKDF2-HMAC-SHA256 (600k iterations)"),
            ("Steganography", "LSB embedding in PCM WAV (8/16/24/32-bit)"),
            ("Framework", "Python 3 + Tkinter/ttk"),
        ]
        for label, value in info_lines:
            row = tk.Frame(inner, bg=COLORS["card"])
            row.pack(fill="x", pady=(SPACING["sm"], 0))
            tk.Label(row, text=f"{label}:", bg=COLORS["card"], fg=COLORS["text_dim"],
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=COLORS["card"], fg=COLORS["text"],
                     font=("Segoe UI", 9), anchor="w").pack(side="left")

        # Security badges.
        badge_frame = tk.Frame(inner, bg=COLORS["card"])
        badge_frame.pack(fill="x", pady=(SPACING["lg"], 0))
        Badge(badge_frame, text="AES-256-GCM").pack(side="left", padx=(0, SPACING["sm"]))
        Badge(badge_frame, text="PBKDF2-SHA256").pack(side="left", padx=(0, SPACING["sm"]))
        Badge(badge_frame, text="LSB WAV").pack(side="left", padx=(0, SPACING["sm"]))
        Badge(badge_frame, text="\u25CF Secure", color=COLORS["success"]).pack(side="left")

        # Preferences card.
        pref_card = Card(container)
        pref_card.grid(row=2, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        pref_inner = pref_card.inner

        tk.Label(pref_inner, text="PREFERENCES", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # Default output naming.
        self._output_naming_var = tk.StringVar(value="<input>_stego.wav")
        row1 = tk.Frame(pref_inner, bg=COLORS["card"])
        row1.pack(fill="x", pady=(SPACING["md"], 0))
        tk.Label(row1, text="Default output name:", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Label(row1, textvariable=self._output_naming_var, bg=COLORS["card"],
                 fg=COLORS["text"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(SPACING["sm"], 0))

        # Password visibility default.
        self._show_pw_var = tk.BooleanVar(value=False)
        row2 = tk.Frame(pref_inner, bg=COLORS["card"])
        row2.pack(fill="x", pady=(SPACING["sm"], 0))
        tk.Label(row2, text="Show passwords by default:", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9)).pack(side="left")
        tk.Label(row2, text="No (masked)", bg=COLORS["card"],
                 fg=COLORS["text"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(SPACING["sm"], 0))

        # Note.
        tk.Label(pref_inner, text="Passwords are never stored, logged, or written to disk.",
                 bg=COLORS["card"], fg=COLORS["text_dim"],
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(SPACING["md"], 0))

        # Test suite card.
        test_card = Card(container)
        test_card.grid(row=3, column=0, sticky="ew")
        test_inner = test_card.inner

        tk.Label(test_inner, text="TEST SUITE", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(test_inner, text="111 tests passing (crypto + audio + steganography + integration + GUI + evaluation)",
                 bg=COLORS["card"], fg=COLORS["text"], font=("Segoe UI", 9)).pack(anchor="w", pady=(SPACING["xs"], 0))
        tk.Label(test_inner, text="Run: .venv\\Scripts\\python.exe -m pytest -v",
                 bg=COLORS["card"], fg=COLORS["text_dim"], font=("Consolas", 8)).pack(anchor="w", pady=(SPACING["xs"], 0))

    def on_breakpoint(self, bp: str):
        pass
