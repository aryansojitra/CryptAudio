"""CryptAudio — Responsive layout engine.

Breakpoints, ResponsiveGrid, ScrollableFrame, and Sidebar with 3 states.
The core of the responsive redesign: everything reflows on resize, nothing clips.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.theme import COLORS, ICONS, SPACING
from gui.widgets import Badge, IconButton


# --------------------------------------------------------------------------- #
# Breakpoints.
# --------------------------------------------------------------------------- #
BREAKPOINT_WIDE = 1100
BREAKPOINT_MEDIUM = 800


def get_breakpoint(width: int) -> str:
    """Return 'wide', 'medium', or 'narrow' based on window width."""
    if width >= BREAKPOINT_WIDE:
        return "wide"
    if width >= BREAKPOINT_MEDIUM:
        return "medium"
    return "narrow"


# --------------------------------------------------------------------------- #
# ScrollableFrame — Canvas + inner Frame + themed scrollbar.
# --------------------------------------------------------------------------- #
class ScrollableFrame(ttk.Frame):
    """A scrollable container. Inner frame width is forced to canvas width.

    Mouse wheel works on Windows/macOS/Linux, only while pointer is over.
    A thin vertical scrollbar appears only when needed.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0, bd=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self.inner = ttk.Frame(self._canvas, style="TFrame")
        self._window_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self.inner.bind("<Configure>", self._on_inner_configure)

        # Mouse wheel binding (Windows/macOS/Linux).
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self._canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self._canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_mousewheel(self, event):
        # Only scroll if pointer is over this widget's area.
        widget = self.winfo_containing(event.x_root, event.y_root)
        if not self._is_child(widget):
            return
        if event.num == 4:  # Linux scroll up
            self._canvas.yview_scroll(-2, "units")
        elif event.num == 5:  # Linux scroll down
            self._canvas.yview_scroll(2, "units")
        elif event.delta:
            self._canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _is_child(self, widget) -> bool:
        """Check if widget is a descendant of this ScrollableFrame."""
        while widget:
            if widget == self:
                return True
            widget = widget.master
        return False

    def scroll_to_top(self):
        self._canvas.yview_moveto(0)


# --------------------------------------------------------------------------- #
# ResponsiveGrid — re-grids children based on available width.
# --------------------------------------------------------------------------- #
class ResponsiveGrid(ttk.Frame):
    """A container that re-grids its children into columns based on width.

    Args:
        parent: Parent widget.
        min_card_width: Minimum width per card before wrapping to fewer columns.
        spacing: Gap between cards.
    """

    def __init__(self, parent, min_card_width: int = 280, spacing: int = SPACING["md"], **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._min_card_width = min_card_width
        self._spacing = spacing
        self._children: list[tk.Widget] = []
        self._columns = 1
        self._forced_columns: int | None = None
        self.bind("<Configure>", self._on_configure)

    def add(self, widget: tk.Widget):
        """Register a child widget for responsive layout."""
        self._children.append(widget)
        self._relayout()

    def _on_configure(self, event):
        if self._forced_columns is not None:
            if self._columns != self._forced_columns:
                self._columns = self._forced_columns
                self._relayout()
            return
        available = max(1, event.width)
        # Every column after the first consumes a gap, so do not squeeze a
        # card below its declared minimum at breakpoint boundaries.
        new_cols = max(1, (available + self._spacing) //
                       (self._min_card_width + self._spacing))
        if new_cols != self._columns:
            self._columns = new_cols
            self._relayout()

    def _relayout(self):
        """Re-grid all children into the current column count."""
        for child in self._children:
            child.grid_forget()

        cols = self._columns
        for c in range(cols):
            self.columnconfigure(c, weight=1, uniform="grid_col")

        for i, child in enumerate(self._children):
            row = i // cols
            col = i % cols
            child.grid(row=row, column=col, sticky="nsew",
                       padx=(0, self._spacing) if col < cols - 1 else 0,
                       pady=(0, self._spacing))

    def set_columns(self, columns: int | None):
        """Force a page-defined column count, or restore width-based sizing."""
        self._forced_columns = max(1, columns) if columns is not None else None
        if self._forced_columns is None:
            self._on_configure(type("Event", (), {"width": self.winfo_width()})())
        else:
            self._columns = self._forced_columns
            self._relayout()

    @property
    def columns(self) -> int:
        return self._columns


# --------------------------------------------------------------------------- #
# Sidebar — 3 responsive states (wide / medium / narrow-hidden).
# --------------------------------------------------------------------------- #
SIDEBAR_WIDTH_WIDE = 220
SIDEBAR_WIDTH_MEDIUM = 72


class NavItem:
    """Data class for a navigation item."""
    def __init__(self, key: str, icon: str, label: str):
        self.key = key
        self.icon = icon
        self.label = label


NAV_ITEMS = [
    NavItem("overview", ICONS["overview"], "Overview"),
    NavItem("embed", ICONS["embed"], "Embed"),
    NavItem("extract", ICONS["extract"], "Extract"),
    NavItem("analysis", ICONS["analysis"], "Analysis"),
    NavItem("settings", ICONS["settings"], "Settings"),
]


class Sidebar(ttk.Frame):
    """Responsive sidebar with 3 states: wide (icon+label), medium (icon), narrow (hidden).

    In narrow mode, the sidebar is hidden and a top bar with hamburger menu is shown.
    """

    def __init__(self, parent, on_navigate=None, **kwargs):
        super().__init__(parent, style="Sidebar.TFrame", **kwargs)
        self._on_navigate = on_navigate or (lambda key: None)
        self._state = "wide"
        self._active_key = "overview"
        self._nav_buttons: dict[str, IconButton] = {}
        self._nav_labels: dict[str, tk.Label] = {}
        self._drawer_open = False

        self._build_brand()
        self._build_nav()
        self._build_footer_badge()
        self._apply_state("wide")

    def _build_brand(self):
        self._brand_frame = tk.Frame(self, bg=COLORS["sidebar"], padx=SPACING["md"], pady=SPACING["lg"])
        self._brand_frame.pack(fill="x")

        self._brand_icon = tk.Label(self._brand_frame, text=ICONS["shield"],
                                    bg=COLORS["sidebar"], fg=COLORS["accent"],
                                    font=("Segoe UI Symbol", 18))
        self._brand_icon.pack(side="left", padx=(0, SPACING["sm"]))

        self._brand_text_frame = tk.Frame(self._brand_frame, bg=COLORS["sidebar"])
        self._brand_text_frame.pack(side="left", fill="x", expand=True)

        self._brand_name = tk.Label(self._brand_text_frame, text="CryptAudio",
                                    bg=COLORS["sidebar"], fg=COLORS["text"],
                                    font=("Segoe UI", 13, "bold"), anchor="w")
        self._brand_name.pack(anchor="w")

        self._brand_sub = tk.Label(self._brand_text_frame, text="Secure Audio Platform",
                                   bg=COLORS["sidebar"], fg=COLORS["text_dim"],
                                   font=("Segoe UI", 8), anchor="w")
        self._brand_sub.pack(anchor="w")

    def _build_nav(self):
        self._nav_frame = tk.Frame(self, bg=COLORS["sidebar"])
        self._nav_frame.pack(fill="both", expand=True, pady=SPACING["md"])

        for item in NAV_ITEMS:
            row = tk.Frame(self._nav_frame, bg=COLORS["sidebar"])
            row.pack(fill="x", padx=SPACING["sm"], pady=2)

            btn = IconButton(row, icon=item.icon, tooltip=item.label,
                             command=lambda k=item.key: self._navigate(k), size=40)
            btn.pack(side="left")
            self._nav_buttons[item.key] = btn

            lbl = tk.Label(row, text=item.label, bg=COLORS["sidebar"],
                           fg=COLORS["text_muted"], font=("Segoe UI", 10),
                           anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True, padx=(SPACING["sm"], 0))
            lbl.bind("<Button-1>", lambda e, k=item.key: self._navigate(k))
            self._nav_labels[item.key] = lbl

    def _build_footer_badge(self):
        self._footer = tk.Frame(self, bg=COLORS["sidebar"], padx=SPACING["md"], pady=SPACING["md"])
        self._footer.pack(fill="x", side="bottom")
        self._secure_badge = Badge(self._footer, text="\u25CF Secure", color=COLORS["success"])
        self._secure_badge.pack(anchor="w")

    def _navigate(self, key: str):
        self.set_active(key)
        self._on_navigate(key)

    def set_active(self, key: str):
        """Highlight the active nav item."""
        self._active_key = key
        for k, btn in self._nav_buttons.items():
            btn.set_active(k == key)
        for k, lbl in self._nav_labels.items():
            lbl.configure(fg=COLORS["text"] if k == key else COLORS["text_muted"])

    def _apply_state(self, state: str):
        """Switch sidebar visual state."""
        self._state = state
        if state == "wide":
            self.configure(width=SIDEBAR_WIDTH_WIDE)
            self._brand_text_frame.pack(side="left", fill="x", expand=True)
            for lbl in self._nav_labels.values():
                lbl.pack(side="left", fill="x", expand=True, padx=(SPACING["sm"], 0))
            self._secure_badge.pack(anchor="w")
        elif state == "medium":
            self.configure(width=SIDEBAR_WIDTH_MEDIUM)
            self._brand_text_frame.pack_forget()
            for lbl in self._nav_labels.values():
                lbl.pack_forget()
            self._secure_badge.pack_forget()
        else:  # narrow — hidden
            self.configure(width=0)
            self._brand_text_frame.pack_forget()
            for lbl in self._nav_labels.values():
                lbl.pack_forget()
            self._secure_badge.pack_forget()

    def set_state(self, state: str):
        if state != self._state:
            self._apply_state(state)

    @property
    def state(self) -> str:
        return self._state

    @property
    def active_key(self) -> str:
        return self._active_key


# --------------------------------------------------------------------------- #
# TopBar — shown in narrow mode (brand + hamburger + badges).
# --------------------------------------------------------------------------- #
class TopBar(ttk.Frame):
    """Top navigation bar for narrow mode: logo, brand, hamburger, badges."""

    def __init__(self, parent, on_menu=None, **kwargs):
        super().__init__(parent, style="TopBar.TFrame", **kwargs)
        self._on_menu = on_menu or (lambda: None)
        self._frame = tk.Frame(self, bg=COLORS["sidebar"], padx=SPACING["md"], pady=SPACING["sm"])
        self._frame.pack(fill="x")

        self._menu_btn = IconButton(self._frame, icon=ICONS["menu"], command=self._on_menu, size=36)
        self._menu_btn.pack(side="left")

        self._brand = tk.Label(self._frame, text="CryptAudio", bg=COLORS["sidebar"],
                               fg=COLORS["text"], font=("Segoe UI", 12, "bold"))
        self._brand.pack(side="left", padx=(SPACING["sm"], 0))

        self._badges_frame = tk.Frame(self._frame, bg=COLORS["sidebar"])
        self._badges_frame.pack(side="right")
        Badge(self._badges_frame, text="AES-256-GCM").pack(side="left", padx=(0, SPACING["sm"]))
        Badge(self._badges_frame, text="\u25CF Secure", color=COLORS["success"]).pack(side="left")


# --------------------------------------------------------------------------- #
# NavDrawer — overlay for narrow mode navigation.
# --------------------------------------------------------------------------- #
class NavDrawer(tk.Toplevel):
    """A navigation drawer overlay shown when hamburger is clicked in narrow mode."""

    def __init__(self, parent, on_navigate=None, current_key: str = "overview"):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=COLORS["sidebar"])
        self._on_navigate = on_navigate or (lambda k: None)

        # Position below the top bar.
        x = parent.winfo_rootx()
        y = parent.winfo_rooty() + 52
        self.geometry(f"+{x}+{y}")

        frame = tk.Frame(self, bg=COLORS["sidebar"], padx=SPACING["md"], pady=SPACING["md"])
        frame.pack(fill="both", expand=True)

        for item in NAV_ITEMS:
            row = tk.Frame(frame, bg=COLORS["sidebar"], cursor="hand2")
            row.pack(fill="x", pady=2)
            icon = tk.Label(row, text=item.icon, bg=COLORS["sidebar"],
                            fg=COLORS["accent"] if item.key == current_key else COLORS["text_muted"],
                            font=("Segoe UI Symbol", 13))
            icon.pack(side="left", padx=(0, SPACING["sm"]))
            lbl = tk.Label(row, text=item.label, bg=COLORS["sidebar"],
                           fg=COLORS["text"] if item.key == current_key else COLORS["text_muted"],
                           font=("Segoe UI", 10), anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            for w in (row, icon, lbl):
                w.bind("<Button-1>", lambda e, k=item.key: self._select(k))

        # Close on clicking outside.
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.focus_set()

    def _select(self, key: str):
        self.destroy()
        self._on_navigate(key)


# --------------------------------------------------------------------------- #
# Footer status bar.
# --------------------------------------------------------------------------- #
class FooterBar(ttk.Frame):
    """Bottom status bar: 'AES-256-GCM | PBKDF2 | LSB WAV | READY'."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style="Footer.TFrame", **kwargs)
        self._frame = tk.Frame(self, bg=COLORS["sidebar"], padx=SPACING["md"], pady=SPACING["xs"])
        self._frame.pack(fill="x")

        self._left = tk.Label(self._frame, text="AES-256-GCM  |  PBKDF2  |  LSB WAV",
                              bg=COLORS["sidebar"], fg=COLORS["text_dim"],
                              font=("Segoe UI", 8), anchor="w")
        self._left.pack(side="left")

        self._right_var = tk.StringVar(value="READY")
        self._right = tk.Label(self._frame, textvariable=self._right_var,
                               bg=COLORS["sidebar"], fg=COLORS["text_muted"],
                               font=("Segoe UI", 8, "bold"), anchor="e")
        self._right.pack(side="right")

    def set_status(self, text: str, color: str = COLORS["text_muted"]):
        self._right_var.set(text)
        self._right.configure(fg=color)
