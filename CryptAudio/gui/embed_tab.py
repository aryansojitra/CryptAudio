"""CryptAudio — Embed page (Phase 6 UI Redesign).

Thin presentation layer over services.cryptaudio_service.embed_message.
All backend logic (threading, queue+poll, validation, error mapping) is
preserved identically to Phase 6 — only the visual layout changes.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from audio.wav_handler import WavError, inspect_wav
from gui.responsive import ResponsiveGrid, ScrollableFrame
from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import (
    Card,
    FileDropCard,
    MetricCard,
    PasswordEntry,
    PrimaryButton,
    SecondaryButton,
    StatusBanner,
    StyledEntry,
    StyledText,
)
from services.cryptaudio_service import (
    AudioError,
    AuthenticationFailureError,
    CapacityExceededError,
    InputValidationError,
    NoHiddenMessageError,
    ServiceError,
    available_capacity_bytes,
    embed_message,
)


# --------------------------------------------------------------------------- #
# Shared helpers (kept from Phase 6 — used by Extract page too).
# --------------------------------------------------------------------------- #
def format_bytes(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def describe_service_error(exc: BaseException) -> str:
    """Map a service exception to a safe, human-readable message."""
    if isinstance(exc, CapacityExceededError):
        return ("Message is too large for the selected audio file. "
                "Please use a larger WAV file or a shorter message.")
    if isinstance(exc, AuthenticationFailureError):
        return "Unable to extract message — incorrect password or corrupted hidden data."
    if isinstance(exc, NoHiddenMessageError):
        return "No valid CryptAudio message was found in this audio file."
    if isinstance(exc, (InputValidationError, AudioError, ServiceError)):
        return str(exc)
    if isinstance(exc, WavError):
        return f"Audio file problem: {exc}"
    return "The operation could not be completed."


def open_folder(path: str) -> None:
    """Best-effort open of a folder in the OS file manager."""
    folder = os.path.dirname(os.path.abspath(path)) or os.path.abspath(path)
    try:
        if hasattr(os, "startfile"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# EmbedPage.
# --------------------------------------------------------------------------- #
class EmbedPage(ttk.Frame):
    """The Embed Message page — responsive dark dashboard layout."""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._app = app
        self._busy = False
        self._worker: threading.Thread | None = None
        self._last_output: str | None = None
        self._results: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._build_vars()
        self._build_ui()

    # -- variables -------------------------------------------------------- #
    def _build_vars(self):
        self.cover_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.channels_var = tk.StringVar(value="--")
        self.rate_var = tk.StringVar(value="--")
        self.width_var = tk.StringVar(value="--")
        self.duration_var = tk.StringVar(value="--")
        self.capacity_var = tk.StringVar(value="--")

        self.msg_size_var = tk.StringVar(value="--")
        self.capacity_status_var = tk.StringVar(value="Waiting for audio")
        self.char_count_var = tk.StringVar(value="0 characters")

    # -- UI construction -------------------------------------------------- #
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        container = ttk.Frame(self, style="TFrame", padding=SPACING["xl"])
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)  # message area expands

        # Title.
        title_frame = ttk.Frame(container, style="TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        tk.Label(title_frame, text="Embed Message", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Encrypt and hide a secret message inside a PCM WAV audio file",
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        # Source audio + info cards (responsive grid).
        self._audio_grid = ResponsiveGrid(container, min_card_width=320)
        self._audio_grid.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["lg"]))

        self._build_source_card()
        self._build_info_card()

        # Secret message.
        self._build_message_card(container, row=2)

        # Password + Output (responsive grid).
        self._security_grid = ResponsiveGrid(container, min_card_width=320)
        self._security_grid.grid(row=3, column=0, sticky="ew", pady=(SPACING["lg"], 0))
        self._build_password_card()
        self._build_output_card()

        # Action bar + status.
        self._build_action_bar(container, row=4)

    def _build_source_card(self):
        card = Card(self._audio_grid)
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="SOURCE AUDIO", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self.file_card = FileDropCard(inner, on_browse=self._browse_cover)
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
                           ("Sample Width", self.width_var), ("Duration", self.duration_var),
                           ("Capacity", self.capacity_var)]:
            mc = MetricCard(self._info_grid, label=label, value="--")
            self._info_grid.add(mc)
            self._info_cards[label] = mc

        self._audio_grid.add(card)

    def _build_message_card(self, container, row):
        card = Card(container)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, SPACING["lg"]))
        inner = card.inner
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        header = tk.Frame(inner, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        tk.Label(header, text="SECRET MESSAGE", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(header, textvariable=self.char_count_var, bg=COLORS["card"],
                 fg=COLORS["text_dim"], font=("Segoe UI", 9)).pack(side="right")

        self.message_text = StyledText(inner, height=7)
        self.message_text.grid(row=1, column=0, sticky="nsew")
        self.message_text.bind_keyrelease(lambda _e: self._refresh_sizes())

        # Capacity indicator.
        self._capacity_frame = tk.Frame(inner, bg=COLORS["card"])
        self._capacity_frame.grid(row=2, column=0, sticky="ew", pady=(SPACING["sm"], 0))
        tk.Label(self._capacity_frame, text="Message size:", bg=COLORS["card"],
                 fg=COLORS["text_dim"], font=("Segoe UI", 9)).pack(side="left")
        tk.Label(self._capacity_frame, textvariable=self.msg_size_var, bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 16))
        tk.Label(self._capacity_frame, text="Status:", bg=COLORS["card"],
                 fg=COLORS["text_dim"], font=("Segoe UI", 9)).pack(side="left")
        self._cap_status_label = tk.Label(self._capacity_frame, textvariable=self.capacity_status_var,
                                          bg=COLORS["card"], fg=COLORS["text_muted"],
                                          font=("Segoe UI", 9, "bold"))
        self._cap_status_label.pack(side="left", padx=(4, 0))

    def _build_password_card(self):
        card = Card(self._security_grid)
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="PASSWORD", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        self.password_entry = PasswordEntry(inner, textvariable=self.password_var)
        self.password_entry.grid(row=1, column=0, sticky="ew")

        tk.Label(inner, text="Used to derive the AES-256 encryption key via PBKDF2",
                 bg=COLORS["card"], fg=COLORS["text_dim"],
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=(SPACING["xs"], 0))

        self._security_grid.add(card)

    def _build_output_card(self):
        card = Card(self._security_grid)
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        tk.Label(inner, text="OUTPUT FILE", bg=COLORS["card"],
                 fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, SPACING["sm"]))

        out_frame = tk.Frame(inner, bg=COLORS["card"])
        out_frame.grid(row=1, column=0, sticky="ew")
        out_frame.columnconfigure(0, weight=1)

        self.output_entry = StyledEntry(out_frame, textvariable=self.output_path_var,
                                        placeholder="Output path...")
        self.output_entry.grid(row=0, column=0, sticky="ew")

        self.save_as_btn = SecondaryButton(out_frame, text="Save As", icon=ICONS["folder"],
                                           command=self._choose_output, min_width=90, height=36)
        self.save_as_btn.grid(row=0, column=1, sticky="e", padx=(SPACING["sm"], 0))

        self._security_grid.add(card)

    def _build_action_bar(self, container, row):
        bar = ttk.Frame(container, style="TFrame")
        bar.grid(row=row, column=0, sticky="ew", pady=(SPACING["lg"], 0))
        bar.columnconfigure(0, weight=1)

        self.status_banner = StatusBanner(bar)
        self.status_banner.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["md"]))

        btn_frame = ttk.Frame(bar, style="TFrame")
        btn_frame.grid(row=1, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)

        self.embed_btn = PrimaryButton(btn_frame, text="Encrypt & Embed", icon=ICONS["embed"],
                                       command=self._on_embed, min_width=180, height=42)
        self.open_folder_btn = SecondaryButton(btn_frame, text="Open Output Folder",
                                               icon=ICONS["folder"],
                                               command=self._open_output_folder,
                                               min_width=150, height=42)
        self.open_folder_btn.set_disabled(True)
        self._action_buttons = (self.open_folder_btn, self.embed_btn)
        self._action_frame = btn_frame
        self._layout_actions("wide")

    # -- responsive callback ---------------------------------------------- #
    def on_breakpoint(self, bp: str):
        """Called by MainWindow when breakpoint changes."""
        columns = 1 if bp == "narrow" else 2
        self._audio_grid.set_columns(columns)
        self._security_grid.set_columns(columns)
        self._layout_actions(bp)

    def _layout_actions(self, bp: str):
        for button in self._action_buttons:
            button.grid_forget()
        if bp == "narrow":
            self._action_frame.columnconfigure(0, weight=1)
            self._action_frame.columnconfigure(1, weight=1)
            self._action_buttons[0].grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
            self._action_buttons[1].grid(row=1, column=0, columnspan=2, sticky="ew")
        else:
            self._action_frame.columnconfigure(0, weight=1)
            self._action_buttons[0].grid(row=0, column=1, sticky="e", padx=(0, SPACING["sm"]))
            self._action_buttons[1].grid(row=0, column=2, sticky="e")

    # -- behaviour -------------------------------------------------------- #
    def _browse_cover(self):
        path = filedialog.askopenfilename(
            title="Select cover WAV audio",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self.cover_path_var.set(path)
        if not self.output_path_var.get():
            folder = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            self.output_path_var.set(os.path.join(folder, f"{base}_stego.wav"))
        self._load_audio_info()

    def _choose_output(self):
        path = filedialog.asksaveasfilename(
            title="Save stego audio as",
            defaultextension=".wav",
            initialfile="stego_audio.wav",
            filetypes=[("WAV audio", "*.wav")],
        )
        if path:
            self.output_path_var.set(path)

    def _load_audio_info(self):
        path = self.cover_path_var.get()
        try:
            info = inspect_wav(path)
            capacity = available_capacity_bytes(path)
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
        self.capacity_var.set(format_bytes(capacity))

        for label, mc in self._info_cards.items():
            mc.set_value(getattr(self, {"Sample Rate": "rate_var", "Channels": "channels_var",
                                        "Sample Width": "width_var", "Duration": "duration_var",
                                        "Capacity": "capacity_var"}[label]).get())

        self._refresh_sizes()
        self.status_banner.clear()
        self._set_app_status("Audio loaded", "success")

    def _reset_metadata(self):
        for var in (self.channels_var, self.rate_var, self.width_var,
                    self.duration_var, self.capacity_var):
            var.set("--")
        for mc in self._info_cards.values():
            mc.set_value("--")
        self.file_card.clear()

    def _refresh_sizes(self):
        message = self._get_message()
        size = len(message.encode("utf-8"))
        self.msg_size_var.set(format_bytes(size) if message else "--")
        self.char_count_var.set(f"{len(message)} characters")
        if self.capacity_var.get() == "--":
            self.capacity_status_var.set("Waiting for audio")
        elif not message:
            self.capacity_status_var.set("Waiting for message")
        elif not self.password_var.get():
            self.capacity_status_var.set("Waiting for password")
        else:
            self.capacity_status_var.set("Ready to embed")

    def _get_message(self) -> str:
        return self.message_text.get()

    def _validate(self) -> str | None:
        if not self.cover_path_var.get().strip():
            return "Please select a cover WAV file."
        if not self._get_message().strip():
            return "Please enter a secret message."
        if not self.password_var.get():
            return "Please enter a password."
        if not self.output_path_var.get().strip():
            return "Please choose an output file."
        return None

    # -- embed workflow (threading preserved) ------------------------------ #
    def _on_embed(self):
        if self._busy:
            return
        error = self._validate()
        if error:
            self.status_banner.set(error, "error")
            self._set_app_status("Validation failed", "error")
            return

        cover = self.cover_path_var.get().strip()
        output = self.output_path_var.get().strip()
        message = self._get_message()
        password = self.password_var.get()

        self._set_busy(True)
        self.status_banner.set("Encrypting and embedding message...", "loading")
        self._set_app_status("EMBEDDING...", "busy")

        self._worker = threading.Thread(
            target=self._embed_worker, args=(cover, output, message, password), daemon=True)
        self._worker.start()
        self._poll_results()

    def _embed_worker(self, cover, output, message, password):
        try:
            result = embed_message(cover, output, message, password)
        except ServiceError as exc:
            self._results.put(("error", exc))
        except Exception:
            self._results.put(("error", None))
        else:
            self._results.put(("success", result))

    def _poll_results(self):
        try:
            kind, payload = self._results.get_nowait()
        except queue.Empty:
            if self._busy:
                self.after(50, self._poll_results)
            return
        if kind == "success":
            self._on_embed_success(payload)
        else:
            self._on_embed_error(payload)

    def _on_embed_success(self, result):
        self._set_busy(False)
        self._last_output = result.output_path
        self.password_var.set("")
        self.capacity_var.set(format_bytes(result.capacity_bytes))
        self.msg_size_var.set(format_bytes(result.encrypted_payload_bytes))
        self.capacity_status_var.set(
            f"Used {format_bytes(result.used_bytes)} of {format_bytes(result.capacity_bytes)}")
        self.status_banner.set(
            f"Message encrypted and embedded successfully \u2192 {os.path.basename(result.output_path)}",
            "success")
        self._set_app_status("EMBEDDED", "success")
        self.open_folder_btn.set_disabled(False)

        # Notify analysis page if available.
        if self._app and hasattr(self._app, "_pages"):
            analysis = self._app._pages.get("analysis")
            if analysis and hasattr(analysis, "set_embed_result"):
                analysis.set_embed_result(result, self.cover_path_var.get())

    def _on_embed_error(self, exc):
        self._set_busy(False)
        msg = describe_service_error(exc) if exc is not None else "An unexpected error occurred."
        self.capacity_status_var.set("Embedding failed")
        self.status_banner.set(msg, "error")
        self._set_app_status("EMBED FAILED", "error")

    def _open_output_folder(self):
        if self._last_output:
            open_folder(self._last_output)

    # -- shared UI helpers ------------------------------------------------ #
    def _set_busy(self, busy: bool):
        self._busy = busy
        self.embed_btn.set_disabled(busy)
        self.save_as_btn.set_disabled(busy)
        self.password_entry.configure_state("disabled" if busy else "normal")
        self.output_entry.configure_state("disabled" if busy else "normal")
        if busy:
            self.open_folder_btn.set_disabled(True)

    def _set_app_status(self, text: str, kind: str = "info"):
        if self._app:
            color = {"success": COLORS["success"], "error": COLORS["error"],
                     "busy": COLORS["warning"]}.get(kind, COLORS["text_muted"])
            self._app.set_status(text, color)


# Compatibility name retained for integrations that imported the pre-redesign
# class. The implementation and public workflow remain the responsive page.
EmbedTab = EmbedPage
