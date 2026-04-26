from __future__ import annotations
import customtkinter as ctk
from typing import Callable

from db import Database
from views.dashboard    import DashboardView
from views.gastos       import GastosView
from views.historial    import HistorialView
from views.tarjetas     import TarjetasView
from views.reportes     import ReportesView
from views.categorias   import CategoriasView
from views.config_view  import ConfigView

# ─────────────────────────────────────────────
# Navigation sidebar
# ─────────────────────────────────────────────

NAV_ITEMS = [
    ('dashboard',  '🏠  Dashboard'),
    ('gastos',     '➕  Nuevo Gasto'),
    ('historial',  '📋  Historial'),
    ('tarjetas',   '💳  Tarjetas'),
    ('reportes',   '📊  Reportes'),
    ('categorias', '🏷️  Categorías'),
    ('config',     '⚙️  Configuración'),
]


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, navigate: Callable):
        super().__init__(parent, width=210, corner_radius=0)
        self.navigate = navigate
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._build()

    def _build(self):
        self.grid_rowconfigure(len(NAV_ITEMS) + 1, weight=1)

        # App title
        title = ctk.CTkLabel(
            self,
            text="💰 GastosApp",
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        title.grid(row=0, column=0, padx=16, pady=(20, 24), sticky="w")

        for i, (key, label) in enumerate(NAV_ITEMS):
            btn = ctk.CTkButton(
                self,
                text=label,
                anchor="w",
                height=38,
                corner_radius=8,
                fg_color="transparent",
                hover_color=("gray75", "gray30"),
                text_color=("gray20", "gray80"),
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self.navigate(k),
            )
            btn.grid(row=i + 1, column=0, padx=10, pady=2, sticky="ew")
            self._buttons[key] = btn

        self.grid_columnconfigure(0, weight=1)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(
                    fg_color=("gray75", "gray30"),
                    font=ctk.CTkFont(size=13, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    font=ctk.CTkFont(size=13),
                )


# ─────────────────────────────────────────────
# Main application window
# ─────────────────────────────────────────────

class GastosApp(ctk.CTk):
    def __init__(self):
        # Apply saved theme before creating the window
        self.db = Database()
        tema = self.db.get_config('tema', 'dark')
        ctk.set_appearance_mode(tema)
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("GastosApp — Control Personal de Gastos")
        self.geometry("1280x720")
        self.minsize(1000, 620)

        self._build_layout()
        self._setup_views()
        self.navigate('dashboard')

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = Sidebar(self, self.navigate)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Top bar
        topbar = ctk.CTkFrame(self, height=46, corner_radius=0, fg_color=("gray85", "gray20"))
        topbar.grid(row=0, column=1, sticky="new")
        topbar.grid_columnconfigure(0, weight=1)
        topbar.grid_propagate(False)

        self.page_title = ctk.CTkLabel(topbar, text="",
                                       font=ctk.CTkFont(size=14))
        self.page_title.grid(row=0, column=0, sticky="w", padx=20)

        theme_btn = ctk.CTkButton(topbar, text="☀️ / 🌙", width=80, height=30,
                                   fg_color="transparent", border_width=1,
                                   text_color=("gray20", "gray80"),
                                   command=self._toggle_theme)
        theme_btn.grid(row=0, column=1, sticky="e", padx=12)

        # Content area (below topbar)
        self.content = ctk.CTkFrame(self, fg_color=("gray92", "gray13"), corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", pady=(46, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._current: str | None = None

    # ─────────────────────────────────────────
    # Views
    # ─────────────────────────────────────────

    def _setup_views(self):
        # Lazy: store factories, create view on first navigation
        self._view_factories = {
            'dashboard':  lambda: DashboardView(self.content, self.db, self.navigate),
            'gastos':     lambda: GastosView(self.content, self.db, self.navigate),
            'historial':  lambda: HistorialView(self.content, self.db, self.navigate),
            'tarjetas':   lambda: TarjetasView(self.content, self.db, self.navigate),
            'reportes':   lambda: ReportesView(self.content, self.db, self.navigate),
            'categorias': lambda: CategoriasView(self.content, self.db, self.navigate),
            'config':     lambda: ConfigView(self.content, self.db, self.navigate,
                                             on_theme_change=self._on_theme_change),
        }
        self._views: dict[str, ctk.CTkFrame] = {}

    def _get_view(self, key: str) -> ctk.CTkFrame:
        if key not in self._views:
            view = self._view_factories[key]()
            view.grid(row=0, column=0, sticky="nsew", padx=20, pady=16)
            view.grid_remove()
            self._views[key] = view
        return self._views[key]

    def navigate(self, key: str, **kwargs):
        if self._current:
            self._views[self._current].grid_remove()

        self._current = key
        view = self._get_view(key)
        view.grid()
        self.update_idletasks()
        if hasattr(view, 'refresh'):
            view.refresh(**kwargs)

        label = next((lbl for k, lbl in NAV_ITEMS if k == key), key)
        self.page_title.configure(text=label.strip())
        self.sidebar.set_active(key)

    # ─────────────────────────────────────────
    # Theme
    # ─────────────────────────────────────────

    def _toggle_theme(self):
        current = ctk.get_appearance_mode().lower()
        new = 'light' if current == 'dark' else 'dark'
        ctk.set_appearance_mode(new)
        self.db.set_config('tema', new)

    def _on_theme_change(self, tema: str):
        ctk.set_appearance_mode(tema)
