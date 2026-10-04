"""CryptAudio — Analysis page (Phase 6 UI Redesign).

Displays Phase 7 audio quality evaluation metrics (MSE, SNR, PSNR, etc.)
after an embed operation. Data comes from the evaluation module via the
EmbedPage — this page never recomputes metrics itself.
"""

from __future__ import annotations

import math
import os
import tkinter as tk
from tkinter import ttk

from gui.embed_tab import format_bytes
from gui.responsive import ResponsiveGrid
from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import Card, MetricCard, StatusBanner


class AnalysisPage(ttk.Frame):
    """The Audio Analysis page — shows quality metrics from the last embed."""

    def __init__(self, parent, app=None, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._app = app
        self._has_data = False
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        container = ttk.Frame(self, style="TFrame", padding=SPACING["xl"])
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)

        # Title.
        title_frame = ttk.Frame(container, style="TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["lg"]))
        tk.Label(title_frame, text="Audio Analysis", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Quality metrics comparing cover vs stego audio (Phase 7 evaluation)",
                 bg=COLORS["bg"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        # Empty state.
        self._empty_label = tk.Label(
            container, text="Run an embed operation to see audio quality metrics.",
            bg=COLORS["bg"], fg=COLORS["text_dim"], font=("Segoe UI", 11))
        self._empty_label.grid(row=1, column=0, sticky="ew", pady=SPACING["2xl"])

        # Metrics grid (hidden until data arrives).
        self._metrics_frame = ttk.Frame(container, style="TFrame")
        self._metrics_frame.columnconfigure(0, weight=1)

        self._metrics_grid = ResponsiveGrid(self._metrics_frame, min_card_width=200)
        self._metrics_grid.grid(row=0, column=0, sticky="ew")

        self._mse_card = MetricCard(self._metrics_grid, label="MSE", value="--",
                                    caption="Mean Squared Error")
        self._snr_card = MetricCard(self._metrics_grid, label="SNR", value="--",
                                    caption="Signal-to-Noise Ratio (dB)")
        self._psnr_card = MetricCard(self._metrics_grid, label="PSNR", value="--",
                                    caption="Peak SNR (dB)")
        self._modified_card = MetricCard(self._metrics_grid, label="Modified Samples", value="--",
                                         caption="Changed / Total")
        self._percent_card = MetricCard(self._metrics_grid, label="Modification %", value="--",
                                        caption="Percentage changed")
        self._maxdiff_card = MetricCard(self._metrics_grid, label="Max Difference", value="--",
                                        caption="Max |original - stego|")

        for mc in (self._mse_card, self._snr_card, self._psnr_card,
                   self._modified_card, self._percent_card, self._maxdiff_card):
            self._metrics_grid.add(mc)

        # File info card.
        self._file_card = Card(self._metrics_frame)
        self._file_card.grid(row=1, column=0, sticky="ew", pady=(SPACING["lg"], 0))
        self._file_inner = self._file_card.inner
        self._file_info_label = tk.Label(self._file_inner, text="", bg=COLORS["card"],
                                         fg=COLORS["text_muted"], font=("Segoe UI", 9),
                                         justify="left", anchor="w")
        self._file_info_label.pack(anchor="w")

    def on_breakpoint(self, bp: str):
        self._metrics_grid.set_columns({"wide": 3, "medium": 2, "narrow": 1}[bp])

    # ------------------------------------------------------------------ #
    # Public API — called by EmbedPage after a successful embed.
    # ------------------------------------------------------------------ #
    def set_embed_result(self, embed_result, cover_path: str = ""):
        """Receive embed result and run evaluation to populate metrics.

        This method calls the evaluation module (read-only) to compute metrics.
        It does NOT recompute crypto/stego logic.
        """
        try:
            from evaluation.audio_quality import compare_audio
            stego_path = embed_result.output_path
            if not os.path.exists(stego_path) or not cover_path:
                return
            quality = compare_audio(cover_path, stego_path)
        except Exception:
            return

        self._has_data = True
        self._empty_label.grid_remove()
        self._metrics_frame.grid(row=1, column=0, sticky="nsew")

        self._mse_card.set_value(f"{quality.mse:.6f}")
        snr = "\u221E" if math.isinf(quality.snr_db) else f"{quality.snr_db:.1f} dB"
        psnr = "\u221E" if math.isinf(quality.psnr_db) else f"{quality.psnr_db:.1f} dB"
        self._snr_card.set_value(snr)
        self._psnr_card.set_value(psnr)
        self._modified_card.set_value(f"{quality.modified_samples:,}")
        self._modified_card.set_caption(f"of {quality.total_samples:,} total")
        self._percent_card.set_value(f"{quality.modification_percentage:.3f}%")
        self._maxdiff_card.set_value(str(quality.max_sample_difference))

        self._file_info_label.configure(
            text=(f"Cover: {os.path.basename(cover_path)}\n"
                  f"Stego: {os.path.basename(stego_path)}\n"
                  f"Payload: {format_bytes(embed_result.encrypted_payload_bytes)} encrypted"))
