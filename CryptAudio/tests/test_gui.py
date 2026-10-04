"""GUI tests for the CryptAudio desktop interface (Phase 6).

These tests focus on **GUI behaviour only** — widget construction, default
state, password masking, input validation, correct delegation to the service
layer (via mocks), and safe error presentation. The 78 backend tests already
cover crypto/audio/steganography/integration, so they are intentionally not
duplicated here.

Heavy backend calls are mocked so no real encryption or large-file embedding
happens during a GUI test. Tests are skipped automatically if no Tk display is
available.

Run the FULL regression suite from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gui import embed_tab as embed_module
from gui import extract_tab as extract_module
from gui.embed_tab import EmbedTab, describe_service_error, format_bytes
from gui.extract_tab import ExtractTab
from gui.main_window import MainWindow
from gui.responsive import get_breakpoint
from services.cryptaudio_service import (
    AuthenticationFailureError,
    CapacityExceededError,
    EmbedResult,
    NoHiddenMessageError,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def _tk():
    """A single hidden Tk root for the whole session.

    Only ONE ``Tk()`` interpreter should exist per process; creating many leads
    to flaky teardown errors ('invalid command name "tcl_findLibrary"'). Tests
    therefore share this root and each gets its own ``Toplevel`` below.
    """
    try:
        win = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - headless environments
        pytest.skip(f"Tk display unavailable: {exc}")
    win.withdraw()
    try:
        yield win
    finally:
        win.destroy()


@pytest.fixture
def root(_tk):
    """A fresh withdrawn Toplevel per test (destroyed afterwards)."""
    top = tk.Toplevel(_tk)
    top.withdraw()
    try:
        yield top
    finally:
        top.destroy()


def _flush(tab, timeout: float = 5.0) -> None:
    """Wait for the worker thread, then drive the main-thread poll loop.

    The worker only enqueues its result; the tab delivers it via a poll loop
    scheduled with ``after`` on the main thread. We join the worker, then pump
    Tk events until the tab is no longer busy (i.e. the result was handled).
    """
    if getattr(tab, "_worker", None) is not None:
        tab._worker.join(timeout=timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        tab.update()
        if not tab._busy:
            break
        time.sleep(0.02)


def _fake_embed_result(output_path: str = "out.wav") -> EmbedResult:
    return EmbedResult(
        output_path=output_path,
        encrypted_payload_bytes=256,
        used_bytes=269,
        capacity_bytes=4096,
        available_payload_bytes=4083,
    )


# --------------------------------------------------------------------------- #
# Construction / structure.
# --------------------------------------------------------------------------- #
def test_main_window_constructs_with_responsive_pages(root):
    win = MainWindow(root)
    assert set(win._pages) == {"overview", "embed", "extract", "analysis", "settings"}
    assert win.current_page == "overview"
    assert win.breakpoint == get_breakpoint(root.winfo_width())
    assert win.footer._right_var.get() == "READY"


def test_main_window_navigation_preserves_page_state(root):
    win = MainWindow(root)
    win._navigate("embed")
    root.update_idletasks()
    page = win._pages["embed"]
    page.message_text.text_widget.insert("1.0", "keep this")
    win._navigate("extract")
    win._navigate("embed")
    assert page.message_text.get() == "keep this"


def test_embed_tab_has_required_widgets(root):
    tab = EmbedTab(root)
    for name in ("file_card", "message_text", "password_entry",
                 "output_entry", "embed_btn", "status_banner", "open_folder_btn"):
        assert hasattr(tab, name), f"EmbedTab missing widget '{name}'"


def test_extract_tab_has_required_widgets(root):
    tab = ExtractTab(root)
    for name in ("file_card", "message_text", "password_entry",
                 "extract_btn", "status_banner"):
        assert hasattr(tab, name), f"ExtractTab missing widget '{name}'"


def test_password_fields_are_masked(root):
    assert str(EmbedTab(root).password_entry.entry.cget("show")) == "\u2022"
    assert str(ExtractTab(root).password_entry.entry.cget("show")) == "\u2022"


def test_embed_default_state_is_valid(root):
    tab = EmbedTab(root)
    assert str(tab.embed_btn.cget("state")) == "normal"
    assert str(tab.open_folder_btn.cget("state")) == "disabled"
    assert tab.channels_var.get() == "--"
    assert tab.capacity_var.get() == "--"
    assert tab.msg_size_var.get() == "--"
    assert tab.capacity_status_var.get() == "Waiting for audio"


def test_extract_message_widget_starts_read_only(root):
    tab = ExtractTab(root)
    assert str(tab.message_text.text_widget.cget("state")) == "disabled"


# --------------------------------------------------------------------------- #
# Input validation (no backend call).
# --------------------------------------------------------------------------- #
def test_embed_validation_blocks_empty_fields(root, monkeypatch):
    tab = EmbedTab(root)
    mock_embed = Mock(return_value=_fake_embed_result())
    monkeypatch.setattr(embed_module, "embed_message", mock_embed)

    tab._on_embed()  # all fields empty

    assert mock_embed.call_count == 0
    assert tab._worker is None
    assert "Please select a cover WAV file" in tab.status_banner._text_label.cget("text")


def test_extract_validation_blocks_empty_fields(root, monkeypatch):
    tab = ExtractTab(root)
    mock_extract = Mock(return_value="secret")
    monkeypatch.setattr(extract_module, "extract_message", mock_extract)

    tab._on_extract()  # all fields empty

    assert mock_extract.call_count == 0
    assert "Please select a stego WAV file" in tab.status_banner._text_label.cget("text")


# --------------------------------------------------------------------------- #
# Correct delegation to the service layer.
# --------------------------------------------------------------------------- #
def test_embed_invokes_service_with_gui_inputs(root, monkeypatch):
    tab = EmbedTab(root)
    mock_embed = Mock(return_value=_fake_embed_result("C:/out/stego.wav"))
    monkeypatch.setattr(embed_module, "embed_message", mock_embed)

    tab.cover_path_var.set("C:/in/cover.wav")
    tab.output_path_var.set("C:/out/stego.wav")
    tab.message_text.text_widget.insert("1.0", "top secret payload")
    tab.password_var.set("hunter2")

    tab._on_embed()
    _flush(tab)

    mock_embed.assert_called_once_with(
        "C:/in/cover.wav", "C:/out/stego.wav", "top secret payload", "hunter2"
    )
    assert "embedded successfully" in tab.status_banner._text_label.cget("text")
    assert "stego.wav" in tab.status_banner._text_label.cget("text")
    assert not tab.open_folder_btn._disabled
    # Password is cleared from the field after a successful embed.
    assert tab.password_var.get() == ""


def test_extract_invokes_service_and_shows_plaintext(root, monkeypatch):
    tab = ExtractTab(root)
    mock_extract = Mock(return_value="recovered plaintext")
    monkeypatch.setattr(extract_module, "extract_message", mock_extract)

    tab.stego_path_var.set("C:/in/stego.wav")
    tab.password_var.set("hunter2")

    tab._on_extract()
    _flush(tab)

    mock_extract.assert_called_once_with("C:/in/stego.wav", "hunter2")
    assert "recovered plaintext" in tab.message_text.get()
    assert "extracted successfully" in tab.status_banner._text_label.cget("text")
    assert tab.password_var.get() == ""


def test_metadata_is_fetched_from_backend_not_duplicated(root, monkeypatch):
    tab = EmbedTab(root)
    fake_info = SimpleNamespace(
        channels=2, frame_rate=44100, sample_width_bits=16, duration_seconds=3.5
    )
    mock_inspect = Mock(return_value=fake_info)
    mock_capacity = Mock(return_value=123456)
    monkeypatch.setattr(embed_module, "inspect_wav", mock_inspect)
    monkeypatch.setattr(embed_module, "available_capacity_bytes", mock_capacity)

    tab.cover_path_var.set("C:/in/cover.wav")
    tab._load_audio_info()

    mock_inspect.assert_called_once_with("C:/in/cover.wav")
    mock_capacity.assert_called_once_with("C:/in/cover.wav")
    assert tab.channels_var.get() == "2"
    assert "44,100" in tab.rate_var.get()
    assert "16-bit" in tab.width_var.get()


# --------------------------------------------------------------------------- #
# Safe error presentation (no class names / tracebacks leaked).
# --------------------------------------------------------------------------- #
def test_embed_capacity_error_is_user_friendly(root, monkeypatch):
    tab = EmbedTab(root)
    monkeypatch.setattr(
        embed_module, "embed_message",
        Mock(side_effect=CapacityExceededError("too big")),
    )
    tab.cover_path_var.set("C:/in/cover.wav")
    tab.output_path_var.set("C:/out/stego.wav")
    tab.message_text.text_widget.insert("1.0", "x" * 10)
    tab.password_var.set("pw")

    tab._on_embed()
    _flush(tab)

    text = tab.status_banner._text_label.cget("text")
    assert "too large" in text
    assert "CapacityExceededError" not in text


def test_extract_wrong_password_is_user_friendly(root, monkeypatch):
    tab = ExtractTab(root)
    monkeypatch.setattr(
        extract_module, "extract_message",
        Mock(side_effect=AuthenticationFailureError("bad tag")),
    )
    tab.stego_path_var.set("C:/in/stego.wav")
    tab.password_var.set("wrong")

    tab._on_extract()
    _flush(tab)

    text = tab.status_banner._text_label.cget("text")
    assert "incorrect password or corrupted hidden data." in text
    assert "AuthenticationFailureError" not in text


def test_extract_clean_wav_reports_no_message(root, monkeypatch):
    tab = ExtractTab(root)
    monkeypatch.setattr(
        extract_module, "extract_message",
        Mock(side_effect=NoHiddenMessageError("none")),
    )
    tab.stego_path_var.set("C:/in/clean.wav")
    tab.password_var.set("pw")

    tab._on_extract()
    _flush(tab)

    assert "No valid CryptAudio message" in tab.status_banner._text_label.cget("text")


@pytest.mark.parametrize(
    "exc, expected_fragment, forbidden",
    [
        (CapacityExceededError("x"), "too large", "CapacityExceededError"),
        (AuthenticationFailureError("x"), "incorrect password",
         "AuthenticationFailureError"),
        (NoHiddenMessageError("x"), "No valid CryptAudio message",
         "NoHiddenMessageError"),
    ],
)
def test_describe_service_error_hides_internals(exc, expected_fragment,
                                                forbidden):
    text = describe_service_error(exc)
    assert expected_fragment in text
    assert forbidden not in text


def test_format_bytes_renders_readable_sizes():
    assert format_bytes(512) == "512 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.00 MB"


@pytest.mark.parametrize(
    "width, expected_bp, expected_sidebar, expected_analysis_columns",
    [
        (1400, "wide", "wide", 3),
        (1200, "wide", "wide", 3),
        (1000, "medium", "medium", 2),
        (900, "medium", "medium", 2),
        (800, "medium", "medium", 2),
        (760, "narrow", "narrow", 1),
    ],
)
def test_responsive_breakpoints_and_analysis_grid(
    root, width, expected_bp, expected_sidebar, expected_analysis_columns
):
    win = MainWindow(root)
    root.deiconify()
    root.geometry(f"{width}x700")
    root.update_idletasks()
    win._apply_breakpoint()
    root.update_idletasks()

    assert win.breakpoint == expected_bp
    assert win.sidebar.state == expected_sidebar
    assert win._pages["analysis"]._metrics_grid.columns == expected_analysis_columns
    assert win.sidebar._nav_buttons["overview"].winfo_width() > 0
    assert win.sidebar._nav_buttons["overview"].winfo_height() > 0

    win._navigate("embed")
    root.update_idletasks()
    page = win._pages["embed"]
    assert page.embed_btn.winfo_ismapped()
    assert page.password_entry.winfo_width() >= 180


def test_resize_preserves_embed_state_and_stacks_audio_cards(root):
    win = MainWindow(root)
    root.deiconify()
    win._navigate("embed")
    page = win._pages["embed"]
    page.cover_path_var.set("C:/in/cover.wav")
    page.message_text.text_widget.insert("1.0", "preserved message")

    root.geometry("1400x900")
    root.update_idletasks()
    win._apply_breakpoint()
    root.geometry("760x560")
    root.update_idletasks()
    win._apply_breakpoint()
    root.update_idletasks()

    assert page.cover_path_var.get() == "C:/in/cover.wav"
    assert page.message_text.get() == "preserved message"
    assert page._audio_grid.columns == 1
    assert page.embed_btn.winfo_ismapped()
