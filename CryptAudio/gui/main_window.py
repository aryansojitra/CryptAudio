"""CryptAudio — main application window (Phase 6).

Builds the top-level Tkinter UI: a header, a :class:`ttk.Notebook` holding the
Embed and Extract tabs, and a shared status bar. This module contains **no**
backend logic — the tabs delegate all real work to
:mod:`services.cryptaudio_service`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.embed_tab import EmbedTab
from gui.extract_tab import ExtractTab

APP_TITLE = "CryptAudio"
APP_SUBTITLE = "Cryptographic Audio Steganography Tool"

EMBED_TAB_LABEL = "\U0001F510 Embed Message"     # 🔐 Embed Message
EXTRACT_TAB_LABEL = "\U0001F513 Extract Message"  # 🔓 Extract Message

# Restrained professional palette (also used by the tabs).
COLORS = {
    "title": "#1f2933",
    "subtitle": "#52606d",
    "accent": "#1f6feb",
    "info": "#3e4c59",
    "success": "#1a7f37",
    "error": "#b42318",
    "busy": "#b54708",
}


class MainWindow:
    """Top-level CryptAudio window hosting the Embed and Extract tabs."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1000x700")
        self.root.minsize(840, 640)

        self._configure_styles()
        self._build_ui()
        self.set_status("Ready")

    # -- styling ---------------------------------------------------------- #
    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass  # fall back to the default theme if 'clam' is unavailable

        base_font = ("Segoe UI", 10)
        style.configure(".", font=base_font)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 20),
                        foreground=COLORS["title"], background="#ffffff")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 11),
                        foreground=COLORS["subtitle"], background="#ffffff")
        style.configure("Header.TFrame", background="#ffffff")
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11),
                        padding=(16, 10), foreground="#ffffff",
                        background=COLORS["accent"])
        style.map("Primary.TButton",
                  background=[("active", "#1a5fd0"), ("disabled", "#9aa5b1")])
        style.configure("Section.TLabelframe", borderwidth=1, relief="solid",
                        padding=10)
        style.configure("Section.TLabelframe.Label",
                        font=("Segoe UI Semibold", 11),
                        foreground=COLORS["accent"])
        style.configure("Status.TLabel", padding=(12, 7),
                        font=("Segoe UI", 10))
        style.configure("Meta.TLabel", font=("Segoe UI", 10))
        style.configure("MetaValue.TLabel", font=("Segoe UI Semibold", 10),
                        foreground=COLORS["title"])

    # -- layout ----------------------------------------------------------- #
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)  # the notebook row expands

        header = ttk.Frame(self.root, style="Header.TFrame", padding=(18, 14))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=APP_SUBTITLE,
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Separator(self.root, orient="horizontal").grid(
            row=1, column=0, sticky="ew"
        )

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=14, pady=(10, 4))

        self.embed_tab = EmbedTab(self.notebook, set_status=self.set_status)
        self.extract_tab = ExtractTab(self.notebook, set_status=self.set_status)
        self.notebook.add(self.embed_tab, text=EMBED_TAB_LABEL)
        self.notebook.add(self.extract_tab, text=EXTRACT_TAB_LABEL)
        self.notebook.select(self.embed_tab)  # start on the Embed tab

        # Bottom status bar (always returns to a useful final state).
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(
            self.root, textvariable=self.status_var, style="Status.TLabel",
            anchor="w", relief="groove",
        )
        self.status_bar.grid(row=3, column=0, sticky="ew")

    # -- shared status ---------------------------------------------------- #
    def set_status(self, text: str, kind: str = "info") -> None:
        """Update the bottom status bar.

        Args:
            text: Status message to display.
            kind: One of 'info', 'success', 'error', 'busy' — controls colour,
                but the meaning is always conveyed by the text as well (so no
                information is colour-only).
        """
        self.status_var.set(text)
        self.status_bar.configure(foreground=COLORS.get(kind, COLORS["info"]))
