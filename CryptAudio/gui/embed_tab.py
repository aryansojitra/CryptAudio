"""CryptAudio — Embed tab (Phase 6).

A thin Tkinter view over :func:`services.cryptaudio_service.embed_message`.
This module performs **no** cryptographic, WAV-parsing or LSB work itself; it
only gathers user input, calls the service, and presents the result. It also
exposes a few shared GUI helpers (:data:`COLORS`, :func:`format_bytes`,
:func:`describe_service_error`) reused by the Extract tab.
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

# Restrained professional palette (shared with the Extract tab).
COLORS = {
    "accent": "#1f6feb",
    "info": "#3e4c59",
    "success": "#1a7f37",
    "error": "#b42318",
    "busy": "#b54708",
    "muted": "#7b8794",
}


def format_bytes(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string (e.g. '120.5 KB')."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def describe_service_error(exc: BaseException) -> str:
    """Map a service exception to a safe, human-readable message.

    Internal exception class names and tracebacks are never surfaced; only the
    user-facing text below (or the service's own friendly message) is shown.
    """
    if isinstance(exc, CapacityExceededError):
        return (
            "\u2717 Message is too large for the selected audio file.\n\n"
            "Please use a larger WAV file or a shorter message."
        )
    if isinstance(exc, AuthenticationFailureError):
        return (
            "\u2717 Unable to extract message.\n\n"
            "Incorrect password or corrupted hidden data."
        )
    if isinstance(exc, NoHiddenMessageError):
        return (
            "\u2717 No valid CryptAudio message was found in this audio file."
        )
    if isinstance(exc, (InputValidationError, AudioError, ServiceError)):
        # These service messages are already written for end users.
        return f"\u2717 {exc}"
    if isinstance(exc, WavError):
        return f"\u2717 Audio file problem: {exc}"
    return "\u2717 The operation could not be completed."


def open_folder(path: str) -> None:
    """Best-effort open of a folder in the OS file manager (no exceptions)."""
    folder = os.path.dirname(os.path.abspath(path)) or os.path.abspath(path)
    try:
        if hasattr(os, "startfile"):        # Windows
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":      # macOS
            subprocess.Popen(["open", folder])
        else:                               # Linux / other
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        pass  # never fail the UI because a folder could not be opened


class EmbedTab(ttk.Frame):
    """The '\U0001F510 Embed Message' tab."""

    def __init__(self, parent, set_status=None) -> None:
        super().__init__(parent, padding=12)
        self._set_status = set_status or (lambda *a, **k: None)
        self._busy = False
        self._worker: threading.Thread | None = None
        self._last_output: str | None = None
        # Workers never touch Tkinter directly; they push results here and a
        # poll loop scheduled on the main thread drains it (thread-safe).
        self._results: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._build_vars()
        self._build_ui()

    # -- construction ----------------------------------------------------- #
    def _build_vars(self) -> None:
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
        self.result_var = tk.StringVar(value="")

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)  # let the message box expand

        self._build_audio_section(0)
        self._build_message_section(1)
        self._build_security_section(2)
        self._build_output_section(3)
        self._build_capacity_section(4)
        self._build_action_bar(5)
        self._build_result_area(6)

    def _section(self, row: int, title: str, sticky: str = "ew") -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self, text=title, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky=sticky, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    # A. Cover WAV selection + metadata ---------------------------------- #
    def _build_audio_section(self, row: int) -> None:
        frame = self._section(row, "Audio")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Cover Audio", style="Meta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.cover_entry = ttk.Entry(frame, textvariable=self.cover_path_var)
        self.cover_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.browse_btn = ttk.Button(
            frame, text="Browse", command=self._browse_cover
        )
        self.browse_btn.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)

        meta = ttk.Frame(frame)
        meta.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for c in range(10):
            meta.columnconfigure(c, weight=1)
        self._meta_labels = [
            ("Channels", self.channels_var),
            ("Sample Rate", self.rate_var),
            ("Sample Width", self.width_var),
            ("Duration", self.duration_var),
            ("Capacity", self.capacity_var),
        ]
        for i, (caption, var) in enumerate(self._meta_labels):
            cell = ttk.Frame(meta)
            cell.grid(row=0, column=i * 2, columnspan=2, sticky="w",
                      padx=(0, 12))
            ttk.Label(cell, text=f"{caption}:", style="Meta.TLabel").pack(
                anchor="w"
            )
            ttk.Label(cell, textvariable=var, style="MetaValue.TLabel").pack(
                anchor="w"
            )

    # B. Secret message ---------------------------------------------------- #
    def _build_message_section(self, row: int) -> None:
        frame = self._section(row, "Secret Message", sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.message_text = tk.Text(
            frame, height=8, wrap="word", undo=True,
            font=("Segoe UI", 11), relief="solid", borderwidth=1, padx=6, pady=6,
        )
        self.message_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self.message_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.message_text.configure(yscrollcommand=scroll.set)
        self.message_text.bind("<KeyRelease>", lambda _e: self._refresh_sizes())

    # C. Password ---------------------------------------------------------- #
    def _build_security_section(self, row: int) -> None:
        frame = self._section(row, "Security")
        ttk.Label(frame, text="Password", style="Meta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var,
                                        show="*")
        self.password_entry.grid(row=0, column=1, sticky="ew", pady=4)

    # D. Output file ------------------------------------------------------- #
    def _build_output_section(self, row: int) -> None:
        frame = self._section(row, "Output")
        ttk.Label(frame, text="Output File", style="Meta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.output_entry = ttk.Entry(frame, textvariable=self.output_path_var)
        self.output_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.save_as_btn = ttk.Button(frame, text="Save As",
                                      command=self._choose_output)
        self.save_as_btn.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)

    # E. Capacity display -------------------------------------------------- #
    def _build_capacity_section(self, row: int) -> None:
        frame = self._section(row, "Capacity")
        rows = [
            ("Audio Capacity:", self.capacity_var),
            ("Message Size:", self.msg_size_var),
            ("Status:", self.capacity_status_var),
        ]
        for i, (caption, var) in enumerate(rows):
            ttk.Label(frame, text=caption, style="Meta.TLabel").grid(
                row=i, column=0, sticky="w", padx=(0, 8), pady=1
            )
            ttk.Label(frame, textvariable=var, style="MetaValue.TLabel").grid(
                row=i, column=1, sticky="w", pady=1
            )
        ttk.Label(
            frame,
            text=("The encrypted payload is slightly larger than the message "
                  "(salt + nonce + auth tag)."),
            style="Meta.TLabel", foreground=COLORS["muted"],
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(6, 0))

    # F. Action bar -------------------------------------------------------- #
    def _build_action_bar(self, row: int) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=row, column=0, sticky="ew", pady=(2, 8))

        self.embed_btn = ttk.Button(
            bar, text="\U0001F510 Embed Message", style="Primary.TButton",
            command=self._on_embed,
        )
        self.embed_btn.pack(side="left")

        self.open_folder_btn = ttk.Button(
            bar, text="Open Output Folder", command=self._open_output_folder,
            state="disabled",
        )
        self.open_folder_btn.pack(side="left", padx=(10, 0))

    def _build_result_area(self, row: int) -> None:
        self.result_label = ttk.Label(
            self, textvariable=self.result_var, justify="left", anchor="w",
            wraplength=900, style="Meta.TLabel",
        )
        self.result_label.grid(row=row, column=0, sticky="ew")

    # -- behaviour -------------------------------------------------------- #
    def _browse_cover(self) -> None:
        path = filedialog.askopenfilename(
            title="Select cover WAV audio",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self.cover_path_var.set(path)
        if not self.output_path_var.get():
            folder = os.path.dirname(path)
            self.output_path_var.set(os.path.join(folder, "stego_audio.wav"))
        self._load_audio_info()

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save stego audio as",
            defaultextension=".wav",
            initialfile="stego_audio.wav",
            filetypes=[("WAV audio", "*.wav")],
        )
        if path:
            self.output_path_var.set(path)

    def _load_audio_info(self) -> None:
        """Read metadata + usable capacity via the backend (no local parsing)."""
        path = self.cover_path_var.get()
        try:
            info = inspect_wav(path)
            capacity = available_capacity_bytes(path)
        except (WavError, ServiceError) as exc:
            self._reset_metadata()
            self._show_result(describe_service_error(exc), "error")
            self._set_status("Could not read the selected audio.", "error")
            return

        self.channels_var.set(str(info.channels))
        self.rate_var.set(f"{info.frame_rate:,} Hz")
        self.width_var.set(f"{info.sample_width_bits}-bit")
        self.duration_var.set(f"{info.duration_seconds:.2f} s")
        self.capacity_var.set(format_bytes(capacity))
        self._refresh_sizes()
        self._show_result("", "info")
        self._set_status("Audio loaded.", "info")

    def _reset_metadata(self) -> None:
        for var in (self.channels_var, self.rate_var, self.width_var,
                    self.duration_var, self.capacity_var):
            var.set("--")

    def _refresh_sizes(self) -> None:
        message = self._get_message()
        size = len(message.encode("utf-8"))
        self.msg_size_var.set(format_bytes(size) if message else "--")
        if self.capacity_var.get() == "--":
            self.capacity_status_var.set("Waiting for audio")
        elif not message:
            self.capacity_status_var.set("Waiting for message")
        elif not self.password_var.get():
            self.capacity_status_var.set("Waiting for password")
        else:
            self.capacity_status_var.set("Ready to embed")

    def _get_message(self) -> str:
        return self.message_text.get("1.0", "end-1c")

    def _validate(self) -> str | None:
        """Light GUI-side validation; deeper checks are the service's job."""
        if not self.cover_path_var.get().strip():
            return "\u2717 Please select a cover WAV file."
        if not self._get_message().strip():
            return "\u2717 Please enter a secret message."
        if not self.password_var.get():
            return "\u2717 Please enter a password."
        if not self.output_path_var.get().strip():
            return "\u2717 Please choose an output file."
        return None

    # -- embed workflow --------------------------------------------------- #
    def _on_embed(self) -> None:
        if self._busy:
            return
        error = self._validate()
        if error:
            self._show_result(error, "error")
            self._set_status("Cannot embed — check the highlighted fields.",
                             "error")
            return

        cover = self.cover_path_var.get().strip()
        output = self.output_path_var.get().strip()
        message = self._get_message()
        password = self.password_var.get()

        self._set_busy(True)
        self._show_result("", "info")
        self._set_status("Encrypting and embedding message...", "busy")
        self._worker = threading.Thread(
            target=self._embed_worker,
            args=(cover, output, message, password),
            daemon=True,
        )
        self._worker.start()
        self._poll_results()

    def _embed_worker(self, cover, output, message, password) -> None:
        # Runs off the main thread: performs NO Tkinter calls, only enqueues.
        try:
            result = embed_message(cover, output, message, password)
        except ServiceError as exc:
            self._results.put(("error", exc))
        except Exception:
            self._results.put(("error", None))
        else:
            self._results.put(("success", result))

    def _poll_results(self) -> None:
        # Always runs on the main thread, so calling after()/widgets is safe.
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

    def _on_embed_success(self, result) -> None:
        self._set_busy(False)
        self._last_output = result.output_path
        self.password_var.set("")  # clear the password once used
        self.capacity_var.set(format_bytes(result.capacity_bytes))
        self.msg_size_var.set(format_bytes(result.encrypted_payload_bytes))
        self.capacity_status_var.set(
            f"Used {format_bytes(result.used_bytes)} of "
            f"{format_bytes(result.capacity_bytes)}"
        )
        self._show_result(
            f"\u2713 Message embedded successfully\n\nOutput:\n{result.output_path}",
            "success",
        )
        self._set_status("Message embedded successfully.", "success")
        self.open_folder_btn.configure(state="normal")

    def _on_embed_error(self, exc) -> None:
        self._set_busy(False)
        message = describe_service_error(exc) if exc is not None else (
            "\u2717 An unexpected error occurred while embedding."
        )
        self.capacity_status_var.set("Embedding failed")
        self._show_result(message, "error")
        self._set_status("Embedding failed.", "error")

    def _open_output_folder(self) -> None:
        if self._last_output:
            open_folder(self._last_output)

    # -- shared UI helpers ------------------------------------------------ #
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.embed_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.save_as_btn.configure(state=state)
        self.password_entry.configure(state=state)
        self.cover_entry.configure(state=state)
        self.output_entry.configure(state=state)
        if busy:
            self.open_folder_btn.configure(state="disabled")

    def _show_result(self, text: str, kind: str) -> None:
        self.result_var.set(text)
        self.result_label.configure(foreground=COLORS.get(kind, COLORS["info"]))
