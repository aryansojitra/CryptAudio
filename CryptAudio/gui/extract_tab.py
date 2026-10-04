"""CryptAudio — Extract page (Phase 6 UI Redesign).

Thin presentation layer over services.cryptaudio_service.extract_message.
All backend logic (threading, queue+poll, validation, error mapping) is
preserved identically — only the visual layout changes.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from audio.wav_handler import WavError, inspect_wav
from gui.embed_tab import describe_service_error, format_bytes
from gui.responsive import ResponsiveGrid
from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import (
    Card,
    FileDropCard,
    MetricCard,
    PasswordEntry,
    PrimaryButton,
    SecondaryButton,
    StatusBanner,
    StyledText,
)
from services.cryptaudio_service import ServiceError, extract_message


class ExtractPage(ttk.Frame):
    """The Extract Message page — responsive dark dashboard layout."""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._app = app
        self._busy = False
        self._worker: threading.Thread | None = None
        self._results: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._build_vars()
        self._build_ui()

    # -- variables -------------------------------------------------------- #
    def _build_vars(self):
        self.stego_path_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.channels_var = tk.StringVar(value="--")
        self.rate_var = tk.StringVar(value="--")
        self.width_var = tk.StringVar(value="--")
        self.duration_var = tk.StringVar(value="--")

    # -- UI construction -------------------------------------------------- #
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        container = ttk.Frame(self, style="TFrame", padding=SPACING["xl"])
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)  # message area expands

        # Title.
        title_frame = ttk.Frame(container, style="TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        tk.Label(title_frame, text="Extract Message", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Recover a hidden encrypted message from a stego WAV file",
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        # Source audio + info cards.
        self._audio_grid = ResponsiveGrid(container, min_card_width=320)
        self._audio_grid.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        self._build_source_card()
        self._build_info_card()

        # Password.
        self._build_password_card(container, row=2)

        # Recovered message.
        self._build_message_card(container, row=3)

        # Action bar + status.
        self._build_action_bar(container, row=4)

    def _build_source_card(self):
        card = Card(self._audio_grid)
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="STEGO AUDIO", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self.file_card = FileDropCard(inner, on_browse=self._browse_stego)
        self.file_card.grid(row=1, column=0, sticky="ew")

        self._audio_grid.add(card)

    def _build_info_card(self):
        card = Card(self._audio_grid)
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="AUDIO INFORMATION", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self._info_grid = ResponsiveGrid(inner, min_card_width=140, spacing=SPACING["sm"])
        self._info_grid.grid(row=1, column=0, sticky="ew")

        self._info_cards = {}
        for label, var in [("Sample Rate", self.rate_var), ("Channels", self.channels_var),
                           ("Sample Width", self.width_var), ("Duration", self.duration_var)]:
            mc = MetricCard(self._info_grid, label=label, value="--")
            self._info_grid.add(mc)
            self._info_cards[label] = mc

        self._audio_grid.add(card)

    def _build_password_card(self, container, row):
        card = Card(container)
        card.grid(row=row, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="PASSWORD", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self.password_entry = PasswordEntry(inner, textvariable=self.password_var)
        self.password_entry.grid(row=1, column=0, sticky="ew")

        tk.Label(inner, text="Must match the password used during embedding",
                 bg=COLORS["card"], fg=COLORS["text_dim"],
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=(SPACING["xs"], 0))

    def _build_message_card(self, container, row):
        card = Card(container)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, SPACING["lg"]))
        inner = card.inner
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        header = tk.Frame(inner, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        tk.Label(header, text="RECOVERED MESSAGE", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(side="left")

        self.copy_btn = SecondaryButton(header, text="Copy", icon=ICONS["copy"],
                                        command=self._copy_message, min_width=80, height=30)
        self.copy_btn.pack(side="right")
        self.copy_btn.set_disabled(True)

        self.message_text = StyledText(inner, height=8, read_only=True)
        self.message_text.grid(row=1, column=0, sticky="nsew")

    def _build_action_bar(self, container, row):
        bar = ttk.Frame(container, style="TFrame")
        bar.grid(row=row, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.status_banner = StatusBanner(bar)
        self.status_banner.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["md"]))

        btn_frame = ttk.Frame(bar, style="TFrame")
        btn_frame.grid(row=1, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)

        self.extract_btn = PrimaryButton(btn_frame, text="Extract Message", icon=ICONS["extract"],
                                         command=self._on_extract, min_width=180, height=42)
        self._action_frame = btn_frame
        self._layout_actions("wide")

    # -- responsive callback ---------------------------------------------- #
    def on_breakpoint(self, bp: str):
        self._audio_grid.set_columns(1 if bp == "narrow" else 2)
        self._layout_actions(bp)

    def _layout_actions(self, bp: str):
        self.extract_btn.grid_forget()
        if bp == "narrow":
            self._action_frame.columnconfigure(0, weight=1)
            self.extract_btn.grid(row=0, column=0, sticky="ew")
        else:
            self._action_frame.columnconfigure(0, weight=1)
            self.extract_btn.grid(row=0, column=1, sticky="e")

    # -- behaviour -------------------------------------------------------- #
    def _browse_stego(self):
        path = filedialog.askopenfilename(
            title="Select stego WAV audio",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self.stego_path_var.set(path)
        self._load_audio_info()

    def _load_audio_info(self):
        path = self.stego_path_var.get()
        try:
            info = inspect_wav(path)
        except (WavError, ServiceError) as exc:
            self._reset_metadata()
            self.status_banner.set(describe_service_error(exc), "error")
            self._set_app_status("Could not read audio", "error")
            return

        self.file_card.set_file(
            os.path.basename(path),
            f"{info.frame_rate:,} Hz \u00B7 {info.channels}ch \u00B7 {info.sample_width_bits}-bit"
        )
        self.channels_var.set(str(info.channels))
        self.rate_var.set(f"{info.frame_rate:,} Hz")
        self.width_var.set(f"{info.sample_width_bits}-bit")
        self.duration_var.set(f"{info.duration_seconds:.2f} s")

        for label, mc in self._info_cards.items():
            mc.set_value(getattr(self, {"Sample Rate": "rate_var", "Channels": "channels_var",
                                        "Sample Width": "width_var", "Duration": "duration_var"}[label]).get())

        self.status_banner.clear()
        self._set_app_status("Audio loaded", "success")

    def _reset_metadata(self):
        for var in (self.channels_var, self.rate_var, self.width_var, self.duration_var):
            var.set("--")
        for mc in self._info_cards.values():
            mc.set_value("--")
        self.file_card.clear()

    def _validate(self) -> str | None:
        if not self.stego_path_var.get().strip():
            return "Please select a stego WAV file."
        if not self.password_var.get():
            return "Please enter a password."
        return None

    # -- extract workflow (threading preserved) ---------------------------- #
    def _on_extract(self):
        if self._busy:
            return
        error = self._validate()
        if error:
            self.status_banner.set(error, "error")
            self._set_app_status("Validation failed", "error")
            return

        stego = self.stego_path_var.get().strip()
        password = self.password_var.get()

        self._set_busy(True)
        self.status_banner.set("Extracting message...", "loading")
        self._set_app_status("EXTRACTING...", "busy")

        self._worker = threading.Thread(
            target=self._extract_worker, args=(stego, password), daemon=True)
        self._worker.start()
        self._poll_results()

    def _extract_worker(self, stego, password):
        try:
            plaintext = extract_message(stego, password)
        except ServiceError as exc:
            self._results.put(("error", exc))
        except Exception:
            self._results.put(("error", None))
        else:
            self._results.put(("success", plaintext))

    def _poll_results(self):
        try:
            kind, payload = self._results.get_nowait()
        except queue.Empty:
            if self._busy:
                self.after(50, self._poll_results)
            return
        if kind == "success":
            self._on_extract_success(payload)
        else:
            self._on_extract_error(payload)

    def _on_extract_success(self, plaintext: str):
        self._set_busy(False)
        self.password_var.set("")
        self.message_text.set(plaintext)
        self.copy_btn.set_disabled(False)
        self.status_banner.set("Message extracted successfully", "success")
        self._set_app_status("EXTRACTED", "success")

    def _on_extract_error(self, exc):
        self._set_busy(False)
        self.message_text.clear()
        self.copy_btn.set_disabled(True)
        msg = describe_service_error(exc) if exc is not None else "An unexpected error occurred."
        self.status_banner.set(msg, "error")
        self._set_app_status("EXTRACT FAILED", "error")

    def _copy_message(self):
        text = self.message_text.get()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_app_status("Copied to clipboard", "success")

    # -- shared UI helpers ------------------------------------------------ #
    def _set_busy(self, busy: bool):
        self._busy = busy
        self.extract_btn.set_disabled(busy)
        self.password_entry.configure_state("disabled" if busy else "normal")

    def _set_app_status(self, text: str, kind: str = "info"):
        if self._app:
            color = {"success": COLORS["success"], "error": COLORS["error"],
                     "busy": COLORS["warning"]}.get(kind, COLORS["text_muted"])
            self._app.set_status(text, color)


# Compatibility name retained for integrations that imported the pre-redesign
# class.
ExtractTab = ExtractPage
