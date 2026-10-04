"""CryptAudio — Main application window (Phase 6 UI Redesign).

Responsive dark dashboard shell: sidebar (3 states), top bar (narrow mode),
page container with ScrollableFrame, and footer status bar. All page content
lives in separate tab modules; this orchestrates navigation and resize.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.responsive import (
    FooterBar,
    NavDrawer,
    ScrollableFrame,
    Sidebar,
    TopBar,
    get_breakpoint,
)
from gui.theme import COLORS, SPACING, build_fonts, configure_styles, set_dpi_awareness
from gui.widgets import Badge


class MainWindow:
    """Top-level CryptAudio responsive dashboard window."""

    def __init__(self, root: tk.Tk) -> None:
        set_dpi_awareness()
        self.root = root
        self.root.title("CryptAudio")
        self.root.geometry("1200x800")
        self.root.minsize(760, 560)
        self.root.configure(bg=COLORS["bg"])

        self._fonts = build_fonts(root)
        self._style = configure_styles(root, self._fonts)

        self._current_page = "overview"
        # Force the first layout pass even when the initial width is wide.
        self._breakpoint = None
        self._pages: dict[str, tk.Widget] = {}
        self._resize_job = None
        self._drawer: NavDrawer | None = None

        self._build_shell()
        self._build_pages()
        self._navigate("overview")
        self._apply_breakpoint()

        # Debounced resize handler.
        self.root.bind("<Configure>", self._on_root_configure)

    # ------------------------------------------------------------------ #
    # Shell layout: sidebar | (topbar + content + footer)
    # ------------------------------------------------------------------ #
    def _build_shell(self):
        self.root.columnconfigure(0, weight=0)  # sidebar
        self.root.columnconfigure(1, weight=1)  # content
        self.root.rowconfigure(0, weight=1)

        # Sidebar.
        self.sidebar = Sidebar(self.root, on_navigate=self._navigate)
        self.sidebar.grid(row=0, column=0, sticky="ns")

        # Content area.
        self._content_frame = ttk.Frame(self.root, style="TFrame")
        self._content_frame.grid(row=0, column=1, sticky="nsew")
        self._content_frame.columnconfigure(0, weight=1)
        self._content_frame.rowconfigure(1, weight=1)

        # Top bar (hidden in wide/medium, shown in narrow).
        self.topbar = TopBar(self._content_frame, on_menu=self._toggle_drawer)
        self.topbar.grid(row=0, column=0, sticky="ew")

        # Scrollable page container.
        self.scroll_area = ScrollableFrame(self._content_frame)
        self.scroll_area.grid(row=1, column=0, sticky="nsew")

        # Footer.
        self.footer = FooterBar(self._content_frame)
        self.footer.grid(row=2, column=0, sticky="ew")

    # ------------------------------------------------------------------ #
    # Pages.
    # ------------------------------------------------------------------ #
    def _build_pages(self):
        """Lazily import and construct all pages."""
        from gui.overview_tab import OverviewPage
        from gui.embed_tab import EmbedPage
        from gui.extract_tab import ExtractPage
        from gui.analysis_tab import AnalysisPage
        from gui.settings_tab import SettingsPage

        container = self.scroll_area.inner
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self._pages["overview"] = OverviewPage(container, app=self)
        self._pages["embed"] = EmbedPage(container, app=self)
        self._pages["extract"] = ExtractPage(container, app=self)
        self._pages["analysis"] = AnalysisPage(container, app=self)
        self._pages["settings"] = SettingsPage(container, app=self)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

    def _navigate(self, key: str):
        """Switch to a page by key."""
        if key not in self._pages:
            return
        self._current_page = key
        for k, page in self._pages.items():
            if k == key:
                page.grid()
                page.tkraise()
            else:
                page.grid_remove()
        self.sidebar.set_active(key)
        self.scroll_area.scroll_to_top()
        self.set_status("READY")
        page = self._pages[key]
        if hasattr(page, "on_breakpoint") and self._breakpoint:
            page.on_breakpoint(self._breakpoint)

    @property
    def current_page(self) -> str:
        return self._current_page

    # ------------------------------------------------------------------ #
    # Responsive resize.
    # ------------------------------------------------------------------ #
    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(50, self._apply_breakpoint)

    def _apply_breakpoint(self):
        self._resize_job = None
        width = self.root.winfo_width()
        bp = get_breakpoint(width)
        if bp == self._breakpoint:
            return
        self._breakpoint = bp

        if bp == "wide":
            self.sidebar.set_state("wide")
            self.sidebar.grid(row=0, column=0, sticky="ns")
            self.topbar.grid_remove()
        elif bp == "medium":
            self.sidebar.set_state("medium")
            self.sidebar.grid(row=0, column=0, sticky="ns")
            self.topbar.grid_remove()
        else:  # narrow
            self.sidebar.set_state("narrow")
            self.sidebar.grid_remove()
            self.topbar.grid()

        # Keep hidden pages ready so navigation never shows a stale layout.
        for page in self._pages.values():
            if hasattr(page, "on_breakpoint"):
                page.on_breakpoint(bp)

    @property
    def breakpoint(self) -> str:
        return self._breakpoint

    # ------------------------------------------------------------------ #
    # Drawer (narrow mode navigation).
    # ------------------------------------------------------------------ #
    def _toggle_drawer(self):
        if self._drawer and self._drawer.winfo_exists():
            self._drawer.destroy()
            self._drawer = None
        else:
            self._drawer = NavDrawer(self.root, on_navigate=self._navigate,
                                     current_key=self._current_page)

    # ------------------------------------------------------------------ #
    # Status.
    # ------------------------------------------------------------------ #
    def set_status(self, text: str, color: str | None = None):
        """Update the footer status bar."""
        self.footer.set_status(text, color or COLORS["text_muted"])

    def set_status_success(self, text: str):
        self.set_status(text, COLORS["success"])

    def set_status_error(self, text: str):
        self.set_status(text, COLORS["error"])

    def set_status_busy(self, text: str):
        self.set_status(text, COLORS["warning"])
