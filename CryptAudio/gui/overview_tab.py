"""CryptAudio — Overview page (Phase 6 UI Redesign).

Welcome/dashboard page with feature cards, quick actions, and security
architecture flow. Purely informational — no backend calls.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.responsive import ResponsiveGrid
from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import Badge, Card, MetricCard, SecondaryButton


class OverviewPage(ttk.Frame):
    """The Overview / Welcome page."""

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
        tk.Label(title_frame, text="Welcome to CryptAudio", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Cryptographic Audio Steganography Tool",
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))

        # Feature cards.
        tk.Label(container, text="SECURITY FEATURES", bg=COLORS["bg"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self._features_grid = ResponsiveGrid(container, min_card_width=260)
        self._features_grid.grid(row=2, column=0, sticky="ew", pady=(0, SPACING["xl"]))

        features = [
            (ICONS["key"], "AES-256-GCM", "Authenticated encryption with associated data", "Active"),
            (ICONS["shield"], "PBKDF2-SHA256", "600,000 iterations key derivation", "Active"),
            (ICONS["wave"], "LSB WAV", "Least-significant-bit audio steganography", "Active"),
        ]
        for icon, title, desc, status in features:
            card = Card(self._features_grid)
            inner = card.inner
            tk.Label(inner, text=icon, bg=COLORS["card"], fg=COLORS["accent"],
                     font=("Segoe UI Symbol", 18)).pack(anchor="w")
            tk.Label(inner, text=title, bg=COLORS["card"], fg=COLORS["text"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(SPACING["xs"], 0))
            tk.Label(inner, text=desc, bg=COLORS["card"], fg=COLORS["text_muted"],
                     font=("Segoe UI", 9), wraplength=240, justify="left").pack(anchor="w", pady=(2, 0))
            Badge(inner, text=f"\u25CF {status}", color=COLORS["success"]).pack(anchor="w", pady=(SPACING["sm"], 0))
            self._features_grid.add(card)

        # Quick actions.
        tk.Label(container, text="QUICK ACTIONS", bg=COLORS["bg"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=3, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self._actions_grid = ResponsiveGrid(container, min_card_width=260)
        self._actions_grid.grid(row=4, column=0, sticky="ew", pady=(0, SPACING["xl"]))

        actions = [
            (ICONS["embed"], "Embed Message", "Encrypt and hide a message in audio", "embed"),
            (ICONS["extract"], "Extract Message", "Recover a hidden message from audio", "extract"),
        ]
        for icon, title, desc, page_key in actions:
            card = Card(self._actions_grid)
            inner = card.inner
            tk.Label(inner, text=icon, bg=COLORS["card"], fg=COLORS["accent"],
                     font=("Segoe UI Symbol", 18)).pack(anchor="w")
            tk.Label(inner, text=title, bg=COLORS["card"], fg=COLORS["text"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(SPACING["xs"], 0))
            tk.Label(inner, text=desc, bg=COLORS["card"], fg=COLORS["text_muted"],
                     font=("Segoe UI", 9), wraplength=240, justify="left").pack(anchor="w", pady=(2, SPACING["sm"]))
            SecondaryButton(inner, text="Open", command=lambda k=page_key: self._navigate(k),
                            min_width=80, height=30).pack(anchor="w")
            self._actions_grid.add(card)

        # Security architecture flow.
        tk.Label(container, text="SECURITY ARCHITECTURE", bg=COLORS["bg"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=5, column=0, sticky="w", pady=(0, SPACING["sm"]))

        flow_card = Card(container)
        flow_card.grid(row=6, column=0, sticky="ew")
        inner = flow_card.inner

        steps = ["Plaintext", "AES-256-GCM", "Encrypted Payload", "LSB Embedding", "Stego WAV"]
        self._flow_frame = tk.Frame(inner, bg=COLORS["card"])
        self._flow_frame.pack(fill="x", pady=SPACING["sm"])
        self._build_flow(steps)

    def _build_flow(self, steps):
        for w in self._flow_frame.winfo_children():
            w.destroy()
        for i, step in enumerate(steps):
            lbl = tk.Label(self._flow_frame, text=step, bg=COLORS["card"],
                           fg=COLORS["text"] if i % 2 == 0 else COLORS["accent"],
                           font=("Segoe UI", 9, "bold" if i % 2 == 0 else "normal"),
                           padx=SPACING["sm"], pady=SPACING["xs"])
            lbl.pack(side="left")
            if i < len(steps) - 1:
                tk.Label(self._flow_frame, text=ICONS["arrow_r"], bg=COLORS["card"],
                         fg=COLORS["text_dim"], font=("Segoe UI", 10)).pack(side="left")

    def _navigate(self, key: str):
        if self._app:
            self._app._navigate(key)

    def on_breakpoint(self, bp: str):
        self._features_grid.set_columns({"wide": 3, "medium": 2, "narrow": 1}[bp])
        self._actions_grid.set_columns(1 if bp == "narrow" else 2)
