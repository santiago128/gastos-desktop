from __future__ import annotations
import customtkinter as ctk
from datetime import date
from tkinter import messagebox
from typing import Callable
import calendar

from db import Database
from utils import format_currency, format_date, periodo_label


class HistorialView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._gastos = []
        self._sort_col = 'fecha'
        self._sort_asc = False
        self._render_gen = 0   # incremented on each new render; cancels stale batches
        self._build()

    # ─────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)   # row 3 = scrollable table (not row 2 = headers)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Historial de Gastos",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="+ Agregar", width=110, height=32,
                      command=lambda: self.navigate('gastos')).grid(row=0, column=2, sticky="e")

        # Filters
        self._build_filters()

        # Table
        self._build_table()

    def _build_filters(self):
        filters = ctk.CTkFrame(self)
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        # Column 4 is an invisible spacer that expands — keeps date filters left, rest right
        filters.grid_columnconfigure(4, weight=1)

        today = date.today()
        months = [f"{m:02d}" for m in range(1, 13)]
        years  = [str(y) for y in range(today.year - 3, today.year + 1)]

        # ── Left group: date filters ──
        ctk.CTkLabel(filters, text="Mes:").grid(row=0, column=0, padx=(12, 4), pady=10)
        self.filter_month = ctk.StringVar(value=f"{today.month:02d}")
        ctk.CTkComboBox(filters, values=["Todos"] + months, variable=self.filter_month,
                        width=72, command=lambda _: self._apply_filters()).grid(row=0, column=1, padx=4)

        ctk.CTkLabel(filters, text="Año:").grid(row=0, column=2, padx=(8, 4))
        self.filter_year = ctk.StringVar(value=str(today.year))
        ctk.CTkComboBox(filters, values=["Todos"] + years, variable=self.filter_year,
                        width=82, command=lambda _: self._apply_filters()).grid(row=0, column=3, padx=4)

        # column 4 = spacer (weight=1, no widget)

        # ── Right group: category + method + search ──
        ctk.CTkLabel(filters, text="Categoría:").grid(row=0, column=5, padx=(8, 4))
        self.filter_cat = ctk.StringVar(value="Todas")
        self.cat_combo = ctk.CTkComboBox(filters, variable=self.filter_cat, width=170,
                                         command=lambda _: self._apply_filters())
        self.cat_combo.grid(row=0, column=6, padx=4)

        ctk.CTkLabel(filters, text="Método:").grid(row=0, column=7, padx=(8, 4))
        self.filter_method = ctk.StringVar(value="Todos")
        ctk.CTkComboBox(filters,
                        values=["Todos", "Efectivo", "Tarjeta de crédito", "Débito/Transferencia"],
                        variable=self.filter_method, width=190,
                        command=lambda _: self._apply_filters()).grid(row=0, column=8, padx=4)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(filters, textvariable=self.search_var, placeholder_text="🔍  Buscar...",
                     width=160).grid(row=0, column=9, padx=(8, 12))

    def _build_table(self):
        # Column headers
        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=2, column=0, sticky="ew")
        # Descripción (col 1) expands; other columns have fixed min-widths
        cols = [
            ("Fecha",       92,  'fecha'),
            ("Descripción", 0,   'descripcion'),   # 0 = expand via weight=1
            ("Categoría",   145, 'categoria'),
            ("Método",      180, 'metodo'),
            ("Tarjeta",     150, 'tarjeta'),
            ("Monto",       120, 'monto'),
            ("",            90,  None),
        ]
        self._col_defs = cols
        header.grid_columnconfigure(1, weight=1)
        for i, (label, width, key) in enumerate(cols):
            kw = {} if width == 0 else {"width": width}
            if key:
                btn = ctk.CTkButton(header, text=label, height=32,
                                    fg_color=("gray80", "gray25"),
                                    text_color=("gray10", "gray90"),
                                    hover_color=("gray70", "gray30"),
                                    font=ctk.CTkFont(size=12, weight="bold"),
                                    command=lambda k=key: self._sort_by(k),
                                    **kw)
                btn.grid(row=0, column=i, padx=(1, 0), sticky="ew")
            else:
                ctk.CTkLabel(header, text="", width=width, height=32).grid(
                    row=0, column=i, padx=(1, 0))

        # Scrollable rows
        self.table_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.table_frame.grid(row=3, column=0, sticky="nsew")
        self.table_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Widget cache — row dicts reused across renders to avoid destroy/create cost
        self._row_cache: list[dict] = []
        self._no_results_lbl: ctk.CTkLabel | None = None

        # Footer
        self.footer_label = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self.footer_label.grid(row=4, column=0, sticky="e", pady=(4, 0))

    # ─────────────────────────────────────────
    # Refresh / Filter
    # ─────────────────────────────────────────

    def refresh(self, reload_cats: bool = True, **_):
        if reload_cats or not hasattr(self, '_categorias'):
            cats = self.db.get_categorias()
            self.cat_combo.configure(values=["Todas"] + [c.nombre for c in cats])
            self._categorias = {c.nombre: c.id for c in cats}
        self._apply_filters()

    def _apply_filters(self):
        moneda = self.db.get_config('moneda', 'COP')

        month = self.filter_month.get()
        year  = self.filter_year.get()
        cat   = self.filter_cat.get()
        method = self.filter_method.get()
        search = self.search_var.get().strip()

        fecha_desde = fecha_hasta = periodo = None
        if year != "Todos" and month != "Todos":
            y, m = int(year), int(month)
            last = calendar.monthrange(y, m)[1]
            fecha_desde = f"{y}-{m:02d}-01"
            fecha_hasta = f"{y}-{m:02d}-{last:02d}"
            periodo = f"{y}-{m:02d}"
        elif year != "Todos":
            fecha_desde = f"{year}-01-01"
            fecha_hasta = f"{year}-12-31"

        cat_id = self._categorias.get(cat) if cat != "Todas" else None
        metodo = method if method != "Todos" else None

        gastos = self.db.get_gastos(
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            categoria_id=cat_id, metodo_pago=metodo,
            busqueda=search if search else None,
            periodo=periodo,
        )
        self._gastos = gastos
        self._render_table(moneda)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col != 'fecha'

        key_map = {
            'fecha':       lambda g: g.fecha,
            'descripcion': lambda g: g.descripcion.lower(),
            'categoria':   lambda g: (g.categoria_nombre or '').lower(),
            'metodo':      lambda g: g.metodo_pago,
            'tarjeta':     lambda g: (g.tarjeta_nombre or ''),
            'monto':       lambda g: g.monto,
        }
        fn = key_map.get(self._sort_col, lambda g: g.fecha)
        self._gastos.sort(key=fn, reverse=not self._sort_asc)
        moneda = self.db.get_config('moneda', 'COP')
        self._render_table(moneda)

    # ─────────────────────────────────────────
    # Row factory  (called once per new slot)
    # ─────────────────────────────────────────

    def _make_row(self, idx: int) -> dict:
        """Create one cached row frame with all child widgets."""
        bg = ("gray88", "gray18") if idx % 2 == 0 else ("gray92", "gray15")
        row_f = ctk.CTkFrame(self.table_frame, fg_color=bg, corner_radius=0)
        row_f.grid(row=idx, column=0, sticky="ew", pady=0)
        self.table_frame.grid_columnconfigure(0, weight=1)
        row_f.grid_columnconfigure(1, weight=1)

        f  = ctk.CTkFont(size=12)
        fb = ctk.CTkFont(size=12, weight="bold")

        lbl_fecha = ctk.CTkLabel(row_f, text="", width=92,  anchor="w", font=f)
        lbl_desc  = ctk.CTkLabel(row_f, text="",            anchor="w", font=f)
        lbl_cat   = ctk.CTkLabel(row_f, text="", width=145, anchor="w", font=f)
        lbl_met   = ctk.CTkLabel(row_f, text="", width=180, anchor="w", font=f)
        lbl_tar   = ctk.CTkLabel(row_f, text="", width=150, anchor="w", font=f)
        lbl_amt   = ctk.CTkLabel(row_f, text="", width=120, anchor="e", font=fb,
                                 text_color="#F44336")

        lbl_fecha.grid(row=0, column=0, padx=8,      pady=6)
        lbl_desc .grid(row=0, column=1, sticky="ew", pady=6, padx=4)
        lbl_cat  .grid(row=0, column=2, padx=4,      pady=6)
        lbl_met  .grid(row=0, column=3, padx=4,      pady=6)
        lbl_tar  .grid(row=0, column=4, padx=4,      pady=6)
        lbl_amt  .grid(row=0, column=5, padx=4,      pady=6)

        btn_frame = ctk.CTkFrame(row_f, fg_color="transparent")
        btn_frame.grid(row=0, column=6, padx=(4, 8))
        btn_edit = ctk.CTkButton(btn_frame, text="✏", width=32, height=28,
                                 fg_color="transparent", border_width=1)
        btn_del  = ctk.CTkButton(btn_frame, text="🗑", width=32, height=28,
                                 fg_color="transparent", border_width=1,
                                 text_color="#F44336")
        btn_edit.pack(side="left", padx=2)
        btn_del .pack(side="left", padx=2)

        return dict(frame=row_f, fecha=lbl_fecha, desc=lbl_desc, cat=lbl_cat,
                    met=lbl_met, tar=lbl_tar, amt=lbl_amt,
                    btn_edit=btn_edit, btn_del=btn_del,
                    _key=None)   # dirty-check key

    # ─────────────────────────────────────────
    # Single-row update with dirty check
    # ─────────────────────────────────────────

    def _update_row(self, i: int, g, moneda: str):
        """Update row i.  Skips all configure() calls if data is unchanged."""
        c   = self._row_cache[i]
        alt = i % 2  # 0 or 1 — encodes stripe colour in key

        desc_text = g.descripcion
        if g.cuota_numero and g.cuotas > 1:
            desc_text = f"{g.descripcion}  •  Cuota {g.cuota_numero}/{g.cuotas}"

        # A tuple that fully describes what would be displayed
        key = (g.id, g.fecha, desc_text,
               g.categoria_nombre, g.metodo_pago,
               g.tarjeta_nombre, g.monto, moneda, alt)

        if c['_key'] == key:
            # Data unchanged — just make sure the row is visible
            if not c['frame'].winfo_ismapped():
                c['frame'].grid()
            return

        # Data changed → update widgets
        c['_key'] = key
        bg = ("gray88", "gray18") if alt == 0 else ("gray92", "gray15")
        c['frame'].configure(fg_color=bg)
        c['frame'].grid()

        c['fecha'].configure(text=format_date(g.fecha))
        c['desc'] .configure(text=desc_text)
        c['cat']  .configure(text=g.categoria_nombre or "—")
        c['met']  .configure(text=g.metodo_pago)
        c['tar']  .configure(text=g.tarjeta_nombre or "—")
        c['amt']  .configure(text=format_currency(g.monto, moneda))

        c['btn_edit'].configure(
            command=lambda gid=g.id: self.navigate(
                'gastos', edit_id=gid, from_view='historial'))
        c['btn_del'].configure(
            command=lambda gid=g.id, desc=g.descripcion: self._delete(gid, desc))

    # ─────────────────────────────────────────
    # Render  (incremental + dirty-check)
    # ─────────────────────────────────────────

    def _render_table(self, moneda: str):
        # Cancel any in-progress incremental render
        self._render_gen += 1
        gen = self._render_gen

        total = sum(g.monto for g in self._gastos)
        self.footer_label.configure(
            text=f"{len(self._gastos)} resultado(s)  ·  Total: {format_currency(total, moneda)}"
        )

        # ── No-results placeholder ──
        if not self._gastos:
            for c in self._row_cache:
                c['frame'].grid_remove()
            if self._no_results_lbl is None:
                self._no_results_lbl = ctk.CTkLabel(
                    self.table_frame,
                    text="Sin resultados para los filtros aplicados.",
                    text_color="gray",
                )
            self._no_results_lbl.grid(row=0, column=0, columnspan=7, pady=30)
            return

        if self._no_results_lbl is not None:
            self._no_results_lbl.grid_remove()

        n = len(self._gastos)

        # Grow widget cache for new rows (one-time cost per new slot)
        while len(self._row_cache) < n:
            self._row_cache.append(self._make_row(len(self._row_cache)))

        # ── First batch: render immediately (instant visual feedback) ──
        BATCH = 30
        first = min(BATCH, n)
        for i in range(first):
            self._update_row(i, self._gastos[i], moneda)

        # ── Rest: schedule in background batches ──
        if n > first:
            self.after(0, lambda: self._render_batch(first, n, moneda, gen, BATCH))
        else:
            self._hide_excess(n)

    def _render_batch(self, start: int, total_n: int, moneda: str,
                      gen: int, batch: int):
        """Background batch renderer — aborts if a newer render was triggered."""
        if gen != self._render_gen:
            return   # stale: a new filter/sort was applied, discard this batch

        end = min(start + batch, total_n)
        for i in range(start, end):
            self._update_row(i, self._gastos[i], moneda)

        if end < total_n:
            self.after(0, lambda: self._render_batch(end, total_n, moneda, gen, batch))
        else:
            self._hide_excess(total_n)

    def _hide_excess(self, visible_n: int):
        """Hide cached rows beyond the current result count."""
        for i in range(visible_n, len(self._row_cache)):
            self._row_cache[i]['frame'].grid_remove()

    def _delete(self, gasto_id: int, desc: str):
        if messagebox.askyesno("Confirmar eliminación",
                               f"¿Eliminar el gasto «{desc}»?\nEsta acción no se puede deshacer."):
            self.db.delete_gasto(gasto_id)
            self._apply_filters()
