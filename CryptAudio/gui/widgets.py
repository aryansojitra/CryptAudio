"""CryptAudio — Custom widgets for the dark dashboard UI.

Reusable, theme-aware widgets built on Canvas/Frame primitives to work around
ttk styling limitations. Every widget respects the dark palette, supports
hover/press/disabled/focus states, and resizes with its parent.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from gui.theme import COLORS, ICONS, SPACING


# --------------------------------------------------------------------------- #
# Card — rounded-look container via Canvas.
# --------------------------------------------------------------------------- #
class Card(ttk.Frame):
    """A card container with a subtle border and rounded appearance.

    Uses a Canvas to draw a rounded rectangle background, with an inner Frame
    hosted via create_window. Resizes with its parent.
    """

    def __init__(self, parent, padding: int = SPACING["lg"], **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self._padding = padding
        self._canvas = tk.Canvas(
            self, bg=COLORS["card"], highlightthickness=0, bd=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._inner = ttk.Frame(self._canvas, style="Card.TFrame")
        self._window_id = self._canvas.create_window(
            (padding, padding), window=self._inner, anchor="nw"
        )
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._draw_rounded_rect()

    @property
    def inner(self) -> ttk.Frame:
        """The inner frame where child widgets should be placed."""
        return self._inner

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._window_id, width=event.width - 2 * self._padding)
        self._draw_rounded_rect()

    def _on_inner_configure(self, _event):
        self._canvas.configure(height=self._inner.winfo_reqheight() + 2 * self._padding)

    def _draw_rounded_rect(self):
        self._canvas.delete("bg_rect")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 2 or h < 2:
            return
        r = 8  # corner radius
        self._canvas.create_polygon(
            r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h,
            r, h, 0, h, 0, h - r, 0, r, 0, 0, r, 0,
            smooth=True, fill=COLORS["card"], outline=COLORS["border"],
            width=1, tags="bg_rect",
        )
        self._canvas.tag_lower("bg_rect")


# --------------------------------------------------------------------------- #
# Buttons — custom hover/press/disabled/focus states.
# --------------------------------------------------------------------------- #
class _BaseButton(tk.Canvas):
    """Base class for custom buttons drawn on Canvas."""

    def __init__(self, parent, text: str, command=None, style: str = "primary",
                 icon: str = "", min_width: int = 120, height: int = 38, **kwargs):
        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)
        self._text = text
        self._command = command
        self._style = style
        self._icon = icon
        self._min_width = min_width
        self._height = height
        self._disabled = False
        self._hovered = False
        self._pressed = False
        self._focused = False

        self._bg = self._get_bg()
        self._fg = self._get_fg()
        self.configure(bg=self._bg, width=max(min_width, self._text_width() + 32), height=height)

        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<space>", self._on_key_activate)
        self.bind("<Return>", self._on_key_activate)
        self.configure(takefocus=True)

    def _get_bg(self) -> str:
        if self._disabled:
            return "#3D3566" if self._style == "primary" else COLORS["card"]
        if self._pressed:
            return COLORS["accent_hover"] if self._style == "primary" else COLORS["card_hover"]
        if self._hovered:
            return COLORS["accent_hover"] if self._style == "primary" else COLORS["card_hover"]
        return COLORS["accent"] if self._style == "primary" else COLORS["card"]

    def _get_fg(self) -> str:
        if self._disabled:
            return "#8B8B9E" if self._style == "primary" else COLORS["text_dim"]
        return "#FFFFFF" if self._style == "primary" else COLORS["text"]

    def _text_width(self) -> int:
        f = tkfont.Font(family="Segoe UI", size=10, weight="bold" if self._style == "primary" else "normal")
        label = f"{self._icon} {self._text}".strip() if self._icon else self._text
        return f.measure(label)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or int(self["width"])
        h = int(self["height"])
        bg = self._get_bg()
        fg = self._get_fg()
        border = COLORS["accent"] if self._style == "primary" else COLORS["border"]
        if self._focused:
            border = COLORS["focus_ring"]

        # Rounded rect background.
        r = 6
        self.create_polygon(
            r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h,
            r, h, 0, h, 0, h - r, 0, r, 0, 0, r, 0,
            smooth=True, fill=bg, outline=border, width=2 if self._focused else 1,
        )

        # Label.
        label = f"{self._icon}  {self._text}".strip() if self._icon else self._text
        self.create_text(w // 2, h // 2, text=label, fill=fg,
                         font=("Segoe UI", 10, "bold" if self._style == "primary" else "normal"))

    def _redraw(self):
        self.configure(bg=self._get_bg())
        self._draw()

    def _on_enter(self, _e):
        if not self._disabled:
            self._hovered = True
            self._redraw()

    def _on_leave(self, _e):
        self._hovered = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _e):
        if not self._disabled:
            self._pressed = True
            self._redraw()

    def _on_release(self, _e):
        if not self._disabled and self._pressed:
            self._pressed = False
            self._redraw()
            if self._command:
                self._command()

    def _on_focus_in(self, _e):
        self._focused = True
        self._redraw()

    def _on_focus_out(self, _e):
        self._focused = False
        self._redraw()

    def _on_key_activate(self, _e):
        if not self._disabled and self._command:
            self._command()
        return "break"

    def set_disabled(self, disabled: bool):
        self._disabled = disabled
        self.configure(state="disabled" if disabled else "normal")
        self._redraw()

    def set_text(self, text: str):
        self._text = text
        self.configure(width=max(self._min_width, self._text_width() + 32))
        self._redraw()


class PrimaryButton(_BaseButton):
    """Accent-colored primary action button."""
    def __init__(self, parent, text: str, command=None, icon: str = "", **kwargs):
        super().__init__(parent, text, command, style="primary", icon=icon, **kwargs)


class SecondaryButton(_BaseButton):
    """Subtle secondary button."""
    def __init__(self, parent, text: str, command=None, icon: str = "", **kwargs):
        super().__init__(parent, text, command, style="secondary", icon=icon, **kwargs)


class IconButton(tk.Canvas):
    """Small icon-only button (for sidebar, toolbars)."""

    def __init__(self, parent, icon: str, command=None, tooltip: str = "",
                 size: int = 40, **kwargs):
        super().__init__(parent, width=size, height=size,
                         highlightthickness=0, bd=0, bg=COLORS["sidebar"], **kwargs)
        self._icon = icon
        self._command = command
        self._tooltip = tooltip
        self._size = size
        self._hovered = False
        self._disabled = False
        self._tooltip_win = None

        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.configure(takefocus=True)
        self.bind("<space>", lambda e: self._on_click(e))
        self.bind("<Return>", lambda e: self._on_click(e))

    def _draw(self):
        self.delete("all")
        bg = COLORS["card_hover"] if self._hovered and not self._disabled else COLORS["sidebar"]
        fg = COLORS["text"] if not self._disabled else COLORS["text_dim"]
        self.create_rectangle(0, 0, self._size, self._size, fill=bg, outline="")
        self.create_text(self._size // 2, self._size // 2, text=self._icon,
                         fill=fg, font=("Segoe UI Symbol", 14))

    def _on_enter(self, _e):
        if not self._disabled:
            self._hovered = True
            self._draw()
            if self._tooltip:
                self._show_tooltip()

    def _on_leave(self, _e):
        self._hovered = False
        self._draw()
        self._hide_tooltip()

    def _on_click(self, _e):
        if not self._disabled and self._command:
            self._command()

    def _show_tooltip(self):
        if self._tooltip_win:
            return
        x = self.winfo_rootx() + self._size + 4
        y = self.winfo_rooty() + self._size // 2 - 12
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self._tooltip_win, text=self._tooltip, bg=COLORS["card"],
                       fg=COLORS["text"], font=("Segoe UI", 9), padx=8, pady=4,
                       relief="solid", bd=1)
        lbl.pack()

    def _hide_tooltip(self):
        if self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    def set_disabled(self, disabled: bool):
        self._disabled = disabled
        self._draw()

    def set_active(self, active: bool):
        """Highlight when this nav item is the active page."""
        self._hovered = active
        self._draw()


# --------------------------------------------------------------------------- #
# StyledEntry / PasswordEntry — dark input with focus border.
# --------------------------------------------------------------------------- #
class StyledEntry(ttk.Frame):
    """A dark-themed entry with border that changes color on focus."""

    def __init__(self, parent, textvariable=None, show: str = "",
                 placeholder: str = "", min_width: int = 180, **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self._placeholder = placeholder
        self._min_width = min_width
        self._has_focus = False
        self._border = tk.Frame(self, bg=COLORS["input_border"], padx=1, pady=1)
        self._border.pack(fill="x", expand=True)
        self._entry = tk.Entry(
            self._border, bg=COLORS["input_bg"], fg=COLORS["text"],
            insertbackground=COLORS["text"], relief="flat",
            font=("Segoe UI", 10), textvariable=textvariable, show=show,
        )
        self._entry.pack(fill="x", expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        # Entry width is a character request; the containing grid may expand it.
        self._entry.configure(width=max(24, min_width // 8))

        if placeholder and (not textvariable or not textvariable.get()):
            self._show_placeholder()

    @property
    def entry(self) -> tk.Entry:
        return self._entry

    def get(self) -> str:
        val = self._entry.get()
        return "" if val == self._placeholder else val

    def set(self, value: str):
        self._entry.delete(0, "end")
        self._entry.insert(0, value)

    def configure_state(self, state: str):
        self._entry.configure(state=state)

    def _on_focus_in(self, _e):
        self._has_focus = True
        self._border.configure(bg=COLORS["focus_ring"])
        if self._placeholder and self._entry.get() == self._placeholder:
            self._entry.delete(0, "end")
            self._entry.configure(fg=COLORS["text"])

    def _on_focus_out(self, _e):
        self._has_focus = False
        self._border.configure(bg=COLORS["input_border"])
        self._show_placeholder()

    def _show_placeholder(self):
        if self._placeholder and not self._entry.get():
            self._entry.insert(0, self._placeholder)
            self._entry.configure(fg=COLORS["text_dim"])


class PasswordEntry(StyledEntry):
    """Masked entry with optional show/hide toggle."""

    def __init__(self, parent, textvariable=None, **kwargs):
        super().__init__(parent, textvariable=textvariable, show="\u2022", **kwargs)
        self._visible = False
        self._toggle_btn = tk.Label(
            self._border, text=ICONS["key"], bg=COLORS["input_bg"],
            fg=COLORS["text_muted"], font=("Segoe UI Symbol", 10), cursor="hand2",
        )
        self._toggle_btn.pack(side="right", padx=(0, SPACING["sm"]))
        self._toggle_btn.bind("<Button-1>", self._toggle_visibility)

    def _toggle_visibility(self, _e):
        self._visible = not self._visible
        self._entry.configure(show="" if self._visible else "\u2022")
        self._toggle_btn.configure(fg=COLORS["accent"] if self._visible else COLORS["text_muted"])


# --------------------------------------------------------------------------- #
# StyledText — dark multiline text with themed scrollbar.
# --------------------------------------------------------------------------- #
class StyledText(ttk.Frame):
    """Dark Text widget with a themed scrollbar that sits directly beside it."""

    def __init__(self, parent, height: int = 8, read_only: bool = False, **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._text = tk.Text(
            self, height=height, wrap="word", bg=COLORS["input_bg"],
            fg=COLORS["text"], insertbackground=COLORS["text"],
            relief="flat", font=("Segoe UI", 10), padx=SPACING["sm"],
            pady=SPACING["sm"], undo=not read_only,
            state="disabled" if read_only else "normal",
        )
        self._text.grid(row=0, column=0, sticky="nsew")

        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._text.yview)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=self._scrollbar.set)
        self._read_only = read_only

    @property
    def text_widget(self) -> tk.Text:
        return self._text

    def get(self) -> str:
        return self._text.get("1.0", "end-1c")

    def set(self, content: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if content:
            self._text.insert("1.0", content)
        if self._read_only:
            self._text.configure(state="disabled")

    def clear(self):
        self.set("")

    def configure_state(self, state: str):
        self._text.configure(state=state)

    def bind_keyrelease(self, callback):
        self._text.bind("<KeyRelease>", callback)


# --------------------------------------------------------------------------- #
# StatusBanner — icon + text + color, never color-only.
# --------------------------------------------------------------------------- #
class StatusBanner(ttk.Frame):
    """A status banner with icon, text, and color. States: idle/loading/success/warning/error."""

    STATE_CONFIG = {
        "idle":    {"icon": ICONS["spinner"], "color": COLORS["text_muted"], "bg": COLORS["card"]},
        "loading": {"icon": ICONS["spinner"], "color": COLORS["warning"],   "bg": COLORS["card"]},
        "success": {"icon": ICONS["check"],   "color": COLORS["success"],   "bg": "#0D2818"},
        "warning": {"icon": ICONS["warning"], "color": COLORS["warning"],   "bg": "#2A2008"},
        "error":   {"icon": ICONS["cross"],   "color": COLORS["error"],     "bg": "#2A0D14"},
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self._state = "idle"
        self._bg_frame = tk.Frame(self, bg=COLORS["card"], padx=SPACING["md"], pady=SPACING["sm"])
        self._bg_frame.pack(fill="x", expand=True)

        self._icon_label = tk.Label(self._bg_frame, text=ICONS["spinner"],
                                    bg=COLORS["card"], fg=COLORS["text_muted"],
                                    font=("Segoe UI Symbol", 12))
        self._icon_label.pack(side="left", padx=(0, SPACING["sm"]))

        self._text_label = tk.Label(self._bg_frame, text="Ready",
                                    bg=COLORS["card"], fg=COLORS["text_muted"],
                                    font=("Segoe UI", 10), anchor="w", justify="left")
        self._text_label.pack(side="left", fill="x", expand=True)

    def set(self, text: str, state: str = "idle"):
        """Update banner text and state."""
        self._state = state
        cfg = self.STATE_CONFIG.get(state, self.STATE_CONFIG["idle"])
        self._bg_frame.configure(bg=cfg["bg"])
        self._icon_label.configure(text=cfg["icon"], bg=cfg["bg"], fg=cfg["color"])
        self._text_label.configure(text=text, bg=cfg["bg"], fg=cfg["color"])

    def clear(self):
        self.set("Ready", "idle")


# --------------------------------------------------------------------------- #
# MetricCard — label + big value + optional caption.
# --------------------------------------------------------------------------- #
class MetricCard(ttk.Frame):
    """Displays a metric: small label, large value, optional caption."""

    def __init__(self, parent, label: str, value: str = "--", caption: str = "", **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self._frame = tk.Frame(self, bg=COLORS["card"], padx=SPACING["lg"], pady=SPACING["md"])
        self._frame.pack(fill="both", expand=True)

        self._label = tk.Label(self._frame, text=label.upper(), bg=COLORS["card"],
                               fg=COLORS["text_muted"], font=("Segoe UI", 9))
        self._label.pack(anchor="w")

        self._value_var = tk.StringVar(value=value)
        self._value = tk.Label(self._frame, textvariable=self._value_var, bg=COLORS["card"],
                               fg=COLORS["text"], font=("Segoe UI", 18, "bold"))
        self._value.pack(anchor="w", pady=(SPACING["xs"], 0))

        self._caption = tk.Label(self._frame, text=caption, bg=COLORS["card"],
                                 fg=COLORS["text_dim"], font=("Segoe UI", 9))
        if caption:
            self._caption.pack(anchor="w")

    def set_value(self, value: str):
        self._value_var.set(value)

    def set_caption(self, caption: str):
        self._caption.configure(text=caption)


# --------------------------------------------------------------------------- #
# Badge — small pill label.
# --------------------------------------------------------------------------- #
class Badge(tk.Label):
    """A small pill-shaped badge (e.g. 'AES-256-GCM', '● Secure')."""

    def __init__(self, parent, text: str, color: str = COLORS["accent2"], **kwargs):
        super().__init__(parent, text=f"  {text}  ", bg=COLORS["sidebar"],
                         fg=color, font=("Segoe UI", 8, "bold"),
                         relief="flat", padx=0, pady=2, **kwargs)


# --------------------------------------------------------------------------- #
# FileDropCard — file selection display.
# --------------------------------------------------------------------------- #
class FileDropCard(ttk.Frame):
    """Shows file selection state: empty prompt or file info + Change button."""

    def __init__(self, parent, on_browse=None, **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)
        self._on_browse = on_browse
        self._frame = tk.Frame(self, bg=COLORS["card"], padx=SPACING["lg"], pady=SPACING["lg"])
        self._frame.pack(fill="both", expand=True)

        self._icon = tk.Label(self._frame, text=ICONS["wave"], bg=COLORS["card"],
                              fg=COLORS["text_dim"], font=("Segoe UI Symbol", 20))
        self._icon.pack(anchor="w")

        self._title = tk.Label(self._frame, text="No audio file selected",
                               bg=COLORS["card"], fg=COLORS["text_muted"],
                               font=("Segoe UI", 11))
        self._title.pack(anchor="w", pady=(SPACING["xs"], 0))

        self._subtitle = tk.Label(self._frame, text="Select a PCM WAV file to continue",
                                  bg=COLORS["card"], fg=COLORS["text_dim"],
                                  font=("Segoe UI", 9))
        self._subtitle.pack(anchor="w")

        self._btn_frame = ttk.Frame(self._frame, style="Card.TFrame")
        self._btn_frame.pack(anchor="w", pady=(SPACING["md"], 0))
        self._browse_btn = SecondaryButton(self._btn_frame, text="Browse",
                                           command=self._do_browse, icon=ICONS["folder"],
                                           min_width=100, height=32)
        self._browse_btn.pack(side="left")

    def _do_browse(self):
        if self._on_browse:
            self._on_browse()

    def set_file(self, filename: str, info: str = ""):
        """Display selected file info."""
        self._icon.configure(text=ICONS["file"], fg=COLORS["accent"])
        self._title.configure(text=filename, fg=COLORS["text"])
        self._subtitle.configure(text=info if info else "File selected")
        self._browse_btn.set_text("Change File")

    def clear(self):
        """Reset to empty state."""
        self._icon.configure(text=ICONS["wave"], fg=COLORS["text_dim"])
        self._title.configure(text="No audio file selected", fg=COLORS["text_muted"])
        self._subtitle.configure(text="Select a PCM WAV file to continue", fg=COLORS["text_dim"])
        self._browse_btn.set_text("Browse")
