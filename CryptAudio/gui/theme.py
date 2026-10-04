"""CryptAudio — Theme module (single source of truth for visual design).

Dark cybersecurity dashboard palette, font stack, spacing scale, and all ttk
style configuration. Every other GUI module imports colors/fonts/spacing from
here — never hardcodes them.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# --------------------------------------------------------------------------- #
# Palette — deep dark, card-based, one accent.
# --------------------------------------------------------------------------- #
COLORS = {
    "bg":           "#0B0F14",   # app background
    "sidebar":      "#10161D",   # sidebar background
    "card":         "#151C24",   # card background
    "card_hover":   "#1A222C",   # card hover
    "border":       "#26313D",   # subtle borders
    "accent":       "#7C5CFF",   # primary accent (purple)
    "accent_hover": "#6A49F2",   # accent hover
    "accent2":      "#25D0A5",   # secondary accent (teal/green)
    "text":         "#F4F7FA",   # primary text
    "text_muted":   "#9AA7B4",   # secondary text
    "text_dim":     "#687583",   # tertiary / disabled text
    "success":      "#25D0A5",   # success state
    "warning":      "#F5B942",   # warning state
    "error":        "#FF647C",   # error state
    "input_bg":     "#0D1117",   # entry/text background
    "input_border": "#303B4A",   # entry border
    "focus_ring":   "#7C5CFF",   # focus indicator
}

# --------------------------------------------------------------------------- #
# Spacing scale (px).
# --------------------------------------------------------------------------- #
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
}

# --------------------------------------------------------------------------- #
# Font stack — Segoe UI on Windows, safe fallback elsewhere.
# --------------------------------------------------------------------------- #
def _resolve_font_family(root: tk.Misc) -> str:
    """Return 'Segoe UI' if available, else a safe sans-serif fallback."""
    try:
        families = set(tkfont.families(root))
    except Exception:
        families = set()
    for candidate in ("Segoe UI", "Helvetica Neue", "Helvetica", "Arial",
                      "DejaVu Sans", "TkDefaultFont"):
        if candidate in families:
            return candidate
    return "TkDefaultFont"


def build_fonts(root: tk.Misc) -> dict:
    """Create and return the application font hierarchy.

    Returns a dict with keys: 'family', 'title', 'subtitle', 'section',
    'body', 'body_bold', 'caption', 'button', 'button_bold', 'icon'.
    """
    family = _resolve_font_family(root)
    return {
        "family": family,
        "title":    (family, 22, "bold"),
        "subtitle": (family, 11),
        "section":  (family, 11, "bold"),
        "body":     (family, 10),
        "body_bold": (family, 10, "bold"),
        "caption":  (family, 9),
        "button":   (family, 10),
        "button_bold": (family, 10, "bold"),
        "icon":     (family, 14),
        "icon_lg":  (family, 18),
    }


# --------------------------------------------------------------------------- #
# Icon glyphs — prefer Segoe MDL2 / Symbol; fallback to ASCII-safe.
# --------------------------------------------------------------------------- #
ICONS = {
    "embed":    "\u25a3",       # secure payload
    "extract":  "\u25c7",       # recovered payload
    "overview": "\u2302",       # home
    "analysis": "\u25a5",       # chart
    "settings": "\u2699",       # gear
    "shield":   "\u25c6",       # shield mark
    "check":    "\u2713",       # ✓
    "cross":    "\u2715",       # ✕
    "warning":  "\u26A0",       # ⚠
    "spinner":  "\u25CC",       # ◌ dotted circle
    "menu":     "\u2630",       # ☰ hamburger
    "copy":     "\u2398",       # copy mark
    "folder":   "\u25a1",       # folder outline
    "wave":     "\u224b",       # waveform
    "key":      "\u2022",       # password visibility control
    "file":     "\u25ab",       # file outline
    "arrow_r":  "\u2192",       # → right arrow
    "arrow_d":  "\u2193",       # ↓ down arrow
}


# --------------------------------------------------------------------------- #
# ttk style configuration.
# --------------------------------------------------------------------------- #
def configure_styles(root: tk.Misc, fonts: dict) -> ttk.Style:
    """Configure all ttk styles for the dark theme. Call once after root exists."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    family = fonts["family"]
    bg = COLORS["bg"]
    card = COLORS["card"]
    border = COLORS["border"]
    text = COLORS["text"]
    muted = COLORS["text_muted"]
    accent = COLORS["accent"]

    # Global defaults.
    style.configure(".", font=fonts["body"], background=bg, foreground=text,
                    bordercolor=border, fieldbackground=COLORS["input_bg"])

    # Frames.
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card)
    style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
    style.configure("TopBar.TFrame", background=COLORS["sidebar"])
    style.configure("Footer.TFrame", background=COLORS["sidebar"])

    # Labels.
    style.configure("TLabel", background=bg, foreground=text, font=fonts["body"])
    style.configure("Card.TLabel", background=card, foreground=text, font=fonts["body"])
    style.configure("Title.TLabel", background=bg, foreground=text, font=fonts["title"])
    style.configure("Subtitle.TLabel", background=bg, foreground=muted, font=fonts["subtitle"])
    style.configure("Section.TLabel", background=card, foreground=muted, font=fonts["section"])
    style.configure("Caption.TLabel", background=card, foreground=muted, font=fonts["caption"])
    style.configure("Accent.TLabel", background=card, foreground=accent, font=fonts["body_bold"])
    style.configure("Muted.TLabel", background=bg, foreground=muted, font=fonts["caption"])
    style.configure("Dim.TLabel", background=bg, foreground=COLORS["text_dim"], font=fonts["caption"])

    # Buttons (base — custom widgets override most of this).
    style.configure("TButton", font=fonts["button"], padding=(SPACING["md"], SPACING["sm"]),
                    background=card, foreground=text, bordercolor=border)
    style.map("TButton",
              background=[("active", COLORS["card_hover"]), ("disabled", card)],
              foreground=[("disabled", COLORS["text_dim"])])

    style.configure("Primary.TButton", font=fonts["button_bold"], padding=(SPACING["lg"], SPACING["sm"]),
                    background=accent, foreground="#FFFFFF", bordercolor=accent)
    style.map("Primary.TButton",
              background=[("active", COLORS["accent_hover"]), ("disabled", "#3D3566")],
              foreground=[("disabled", "#8B8B9E")])

    style.configure("Secondary.TButton", font=fonts["button"], padding=(SPACING["md"], SPACING["sm"]),
                    background="transparent", foreground=text, bordercolor=border)
    style.map("Secondary.TButton",
              background=[("active", COLORS["card_hover"])],
              bordercolor=[("active", accent)])

    # Entry.
    style.configure("TEntry", fieldbackground=COLORS["input_bg"], foreground=text,
                    bordercolor=COLORS["input_border"], insertcolor=text,
                    padding=(SPACING["sm"], SPACING["sm"]))
    style.map("TEntry", bordercolor=[("focus", accent)])

    # Notebook (hidden — we use sidebar navigation instead).
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", font=fonts["body"], padding=(SPACING["md"], SPACING["sm"]),
                    background=card, foreground=muted)
    style.map("TNotebook.Tab",
              background=[("selected", accent)],
              foreground=[("selected", "#FFFFFF")])

    # Separator.
    style.configure("TSeparator", background=border)

    # Scrollbar.
    style.configure("Vertical.TScrollbar", background=COLORS["border"],
                    troughcolor=bg, bordercolor=bg, arrowcolor=muted)
    style.map("Vertical.TScrollbar", background=[("active", COLORS["text_dim"])])

    # Progressbar.
    style.configure("TProgressbar", background=accent, troughcolor=COLORS["input_bg"],
                    bordercolor=border, lightcolor=accent, darkcolor=accent)

    return style


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def set_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness on Windows (no-op elsewhere)."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass  # best-effort


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def lighten(hex_color: str, factor: float = 0.15) -> str:
    """Lighten a hex color by a factor (0-1)."""
    r, g, b = hex_to_rgb(hex_color)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_color: str, factor: float = 0.15) -> str:
    """Darken a hex color by a factor (0-1)."""
    r, g, b = hex_to_rgb(hex_color)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"
