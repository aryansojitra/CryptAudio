"""CryptAudio — Extract tab (Phase 6).

A thin Tkinter view over :func:`services.cryptaudio_service.extract_message`.
No cryptographic or LSB logic lives here — the tab collects a stego WAV and a
password, calls the service, and presents the plaintext (or a safe, friendly
error). Shared GUI helpers are imported from :mod:`gui.embed_tab`.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from audio.wav_handler import WavError, inspect_wav
from gui.embed_tab import COLORS, describe_service_error
from services.cryptaudio_service import ServiceError, extract_message


class ExtractTab(ttk.Frame):
    """The '\U0001F513 Extract Message' tab."""

    def __init__(self, parent, set_status=None) -> None:
        super().__init__(parent, padding=12)
        self._set_status = set_status or (lambda *a, **k: None)
        self._busy = False
        self._worker: threading.Thread | None = None
        # Workers never touch Tkinter directly; they push results here and a
        # poll loop scheduled on the main thread drains it (thread-safe).
        self._results: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._build_vars()
        self._build_ui()

    # -- construction ----------------------------------------------------- #
    def _build_vars(self) -> None:
        self.stego_path_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.channels_var = tk.StringVar(value="--")
        self.rate_var = tk.StringVar(value="--")
        self.width_var = tk.StringVar(value="--")
        self.duration_var = tk.StringVar(value="--")

        self.result_var = tk.StringVar(value="")

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)  # let the message box expand

        self._build_audio_section(0)
        self._build_security_section(1)
        self._build_message_section(2)
        self._build_action_bar(3)
        self._build_result_area(4)

    def _section(self, row: int, title: str, sticky: str = "ew") -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self, text=title, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky=sticky, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    # A. Stego WAV selection + info ---------------------------------------- #
    def _build_audio_section(self, row: int) -> None:
        frame = self._section(row, "Audio")
        ttk.Label(frame, text="Stego Audio", style="Meta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.stego_entry = ttk.Entry(frame, textvariable=self.stego_path_var)
        self.stego_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.browse_btn = ttk.Button(frame, text="Browse",
                                     command=self._browse_stego)
        self.browse_btn.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)

        meta = ttk.Frame(frame)
        meta.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for c in range(8):
            meta.columnconfigure(c, weight=1)
        self._meta_labels = [
            ("Channels", self.channels_var),
            ("Sample Rate", self.rate_var),
            ("Sample Width", self.width_var),
            ("Duration", self.duration_var),
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

    # C. Password ---------------------------------------------------------- #
    def _build_security_section(self, row: int) -> None:
        frame = self._section(row, "Security")
        ttk.Label(frame, text="Password", style="Meta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4
        )
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var,
                                        show="*")
        self.password_entry.grid(row=0, column=1, sticky="ew", pady=4)

    # Extracted message area (read-only, but selectable/copyable) ---------- #
    def _build_message_section(self, row: int) -> None:
        frame = self._section(row, "Extracted Message", sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.message_text = tk.Text(
            frame, height=10, wrap="word", font=("Segoe UI", 11),
            relief="solid", borderwidth=1, padx=6, pady=6, state="disabled",
            background="#fbfcfd",
        )
        self.message_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self.message_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.message_text.configure(yscrollcommand=scroll.set)

    # D. Action bar -------------------------------------------------------- #
    def _build_action_bar(self, row: int) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=row, column=0, sticky="ew", pady=(2, 8))
        self.extract_btn = ttk.Button(
            bar, text="\U0001F513 Extract Message", style="Primary.TButton",
            command=self._on_extract,
        )
        self.extract_btn.pack(side="left")
        self.copy_btn = ttk.Button(bar, text="Copy", command=self._copy_message,
                                   state="disabled")
        self.copy_btn.pack(side="left", padx=(10, 0))

    def _build_result_area(self, row: int) -> None:
        self.result_label = ttk.Label(
            self, textvariable=self.result_var, justify="left", anchor="w",
            wraplength=900, style="Meta.TLabel",
        )
        self.result_label.grid(row=row, column=0, sticky="ew")

    # -- behaviour -------------------------------------------------------- #
    def _browse_stego(self) -> None:
        path = filedialog.askopenfilename(
            title="Select stego WAV audio",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return
        self.stego_path_var.set(path)
        self._load_audio_info()

    def _load_audio_info(self) -> None:
        path = self.stego_path_var.get()
        try:
            info = inspect_wav(path)
        except (WavError, ServiceError) as exc:
            self._reset_metadata()
            self._show_result(describe_service_error(exc), "error")
            self._set_status("Could not read the selected audio.", "error")
            return

        self.channels_var.set(str(info.channels))
        self.rate_var.set(f"{info.frame_rate:,} Hz")
        self.width_var.set(f"{info.sample_width_bits}-bit")
        self.duration_var.set(f"{info.duration_seconds:.2f} s")
        self._show_result("", "info")
        self._set_status("Audio loaded.", "info")

    def _reset_metadata(self) -> None:
        for var in (self.channels_var, self.rate_var, self.width_var,
                    self.duration_var):
            var.set("--")

    def _validate(self) -> str | None:
        if not self.stego_path_var.get().strip():
            return "\u2717 Please select a stego WAV file."
        if not self.password_var.get():
            return "\u2717 Please enter a password."
        return None

    # -- extract workflow ------------------------------------------------- #
    def _on_extract(self) -> None:
        if self._busy:
            return
        error = self._validate()
        if error:
            self._show_result(error, "error")
            self._set_status("Cannot extract — check the highlighted fields.",
                             "error")
            return

        stego = self.stego_path_var.get().strip()
        password = self.password_var.get()

        self._set_busy(True)
        self._show_result("", "info")
        self._set_status("Extracting message...", "busy")
        self._worker = threading.Thread(
            target=self._extract_worker, args=(stego, password), daemon=True,
        )
        self._worker.start()
        self._poll_results()

    def _extract_worker(self, stego, password) -> None:
        # Runs off the main thread: performs NO Tkinter calls, only enqueues.
        try:
            plaintext = extract_message(stego, password)
        except ServiceError as exc:
            self._results.put(("error", exc))
        except Exception:
            self._results.put(("error", None))
        else:
            self._results.put(("success", plaintext))

    def _poll_results(self) -> None:
        # Always runs on the main thread, so calling after()/widgets is safe.
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

    def _on_extract_success(self, plaintext: str) -> None:
        self._set_busy(False)
        self.password_var.set("")  # clear the password once used
        self._set_message_text(plaintext)
        self._show_result("\u2713 Message extracted successfully", "success")
        self._set_status("Message extracted successfully.", "success")

    def _on_extract_error(self, exc) -> None:
        self._set_busy(False)
        self._set_message_text("")
        message = describe_service_error(exc) if exc is not None else (
            "\u2717 An unexpected error occurred while extracting."
        )
        self._show_result(message, "error")
        self._set_status("Extraction failed.", "error")

    def _set_message_text(self, text: str) -> None:
        self.message_text.configure(state="normal")
        self.message_text.delete("1.0", "end")
        if text:
            self.message_text.insert("1.0", text)
        self.message_text.configure(state="disabled")
        self.copy_btn.configure(state="normal" if text else "disabled")

    def _copy_message(self) -> None:
        text = self.message_text.get("1.0", "end-1c")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status("Extracted message copied to clipboard.", "info")

    # -- shared UI helpers ------------------------------------------------ #
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.extract_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.password_entry.configure(state=state)
        self.stego_entry.configure(state=state)

    def _show_result(self, text: str, kind: str) -> None:
        self.result_var.set(text)
        self.result_label.configure(foreground=COLORS.get(kind, COLORS["info"]))
