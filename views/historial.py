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
        self._build()

    # ─────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

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
        filters.grid_columnconfigure(4, weight=1)

        today = date.today()
        months = [f"{m:02d}" for m in range(1, 13)]
        years  = [str(y) for y in range(today.year - 3, today.year + 1)]

        ctk.CTkLabel(filters, text="Mes:").grid(row=0, column=0, padx=(12, 4), pady=10)
        self.filter_month = ctk.StringVar(value=f"{today.month:02d}")
        ctk.CTkComboBox(filters, values=["Todos"] + months, variable=self.filter_month,
                        width=70, command=lambda _: self._apply_filters()).grid(row=0, column=1, padx=4)

        ctk.CTkLabel(filters, text="Año:").grid(row=0, column=2, padx=(8, 4))
        self.filter_year = ctk.StringVar(value=str(today.year))
        ctk.CTkComboBox(filters, values=["Todos"] + years, variable=self.filter_year,
                        width=80, command=lambda _: self._apply_filters()).grid(row=0, column=3, padx=4)

        ctk.CTkLabel(filters, text="Categoría:").grid(row=0, column=4, padx=(8, 4))
        self.filter_cat = ctk.StringVar(value="Todas")
        self.cat_combo = ctk.CTkComboBox(filters, variable=self.filter_cat, width=160,
                                         command=lambda _: self._apply_filters())
        self.cat_combo.grid(row=0, column=5, padx=4)

        ctk.CTkLabel(filters, text="Método:").grid(row=0, column=6, padx=(8, 4))
        self.filter_method = ctk.StringVar(value="Todos")
        ctk.CTkComboBox(filters,
                        values=["Todos", "Efectivo", "Tarjeta de crédito", "Débito/Transferencia"],
                        variable=self.filter_method, width=180,
                        command=lambda _: self._apply_filters()).grid(row=0, column=7, padx=4)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(filters, textvariable=self.search_var, placeholder_text="Buscar...",
                     width=150).grid(row=0, column=8, padx=(8, 12))

    def _build_table(self):
        # Column headers
        header = ctk.CTkFrame(self)
        header.grid(row=2, column=0, sticky="ew")
        cols = [
            ("Fecha",       90,  'fecha'),
            ("Descripción", 250, 'descripcion'),
            ("Categoría",   140, 'categoria'),
            ("Método",      160, 'metodo'),
            ("Tarjeta",     160, 'tarjeta'),
            ("Monto",       110, 'monto'),
            ("",            90,  None),
        ]
        self._col_defs = cols
        header.grid_columnconfigure(1, weight=1)
        for i, (label, width, key) in enumerate(cols):
            if key:
                btn = ctk.CTkButton(header, text=label, width=width, height=30,
                                    fg_color=("gray80", "gray25"),
                                    text_color=("gray10", "gray90"),
                                    hover_color=("gray70", "gray30"),
                                    command=lambda k=key: self._sort_by(k))
                btn.grid(row=0, column=i, padx=(1, 0), sticky="ew")
            else:
                ctk.CTkLabel(header, text="", width=width).grid(row=0, column=i, padx=(1, 0))
        header.grid_columnconfigure(1, weight=1)

        # Scrollable rows
        self.table_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.table_frame.grid(row=3, column=0, sticky="nsew")
        self.table_frame.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Footer
        self.footer_label = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self.footer_label.grid(row=4, column=0, sticky="e", pady=(4, 0))

    # ─────────────────────────────────────────
    # Refresh / Filter
    # ─────────────────────────────────────────

    def refresh(self, **_):
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

        fecha_desde = fecha_hasta = None
        if year != "Todos" and month != "Todos":
            y, m = int(year), int(month)
            last = calendar.monthrange(y, m)[1]
            fecha_desde = f"{y}-{m:02d}-01"
            fecha_hasta = f"{y}-{m:02d}-{last:02d}"
        elif year != "Todos":
            fecha_desde = f"{year}-01-01"
            fecha_hasta = f"{year}-12-31"

        cat_id = self._categorias.get(cat) if cat != "Todas" else None
        metodo = method if method != "Todos" else None

        gastos = self.db.get_gastos(
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            categoria_id=cat_id, metodo_pago=metodo,
            busqueda=search if search else None,
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

    def _render_table(self, moneda: str):
        for w in self.table_frame.winfo_children():
            w.destroy()

        total = sum(g.monto for g in self._gastos)
        self.footer_label.configure(
            text=f"{len(self._gastos)} resultado(s)  ·  Total: {format_currency(total, moneda)}"
        )

        if not self._gastos:
            ctk.CTkLabel(self.table_frame, text="Sin resultados para los filtros aplicados.",
                         text_color="gray").grid(row=0, column=0, columnspan=7, pady=30)
            return

        for i, g in enumerate(self._gastos):
            bg = ("gray88", "gray18") if i % 2 == 0 else ("gray92", "gray15")
            row_f = ctk.CTkFrame(self.table_frame, fg_color=bg, corner_radius=0)
            row_f.grid(row=i, column=0, sticky="ew", pady=0)
            self.table_frame.grid_columnconfigure(0, weight=1)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=format_date(g.fecha), width=90,
                         anchor="w").grid(row=0, column=0, padx=8, pady=5)
            ctk.CTkLabel(row_f, text=g.descripcion, anchor="w").grid(
                row=0, column=1, sticky="ew", padx=4, pady=5)
            ctk.CTkLabel(row_f, text=g.categoria_nombre or "—",
                         width=140, anchor="w").grid(row=0, column=2, padx=4, pady=5)
            ctk.CTkLabel(row_f, text=g.metodo_pago, width=160,
                         anchor="w").grid(row=0, column=3, padx=4, pady=5)
            ctk.CTkLabel(row_f, text=g.tarjeta_nombre or "—", width=140,
                         anchor="w").grid(row=0, column=4, padx=4, pady=5)
            ctk.CTkLabel(row_f, text=format_currency(g.monto, moneda),
                         width=110, anchor="e",
                         text_color="#F44336").grid(row=0, column=5, padx=4, pady=5)

            btn_frame = ctk.CTkFrame(row_f, fg_color="transparent")
            btn_frame.grid(row=0, column=6, padx=(4, 8))
            ctk.CTkButton(btn_frame, text="✏", width=30, height=26,
                          fg_color="transparent", border_width=1,
                          command=lambda gid=g.id: self.navigate('gastos', edit_id=gid)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(btn_frame, text="🗑", width=30, height=26,
                          fg_color="transparent", border_width=1,
                          text_color="#F44336",
                          command=lambda gid=g.id, desc=g.descripcion: self._delete(gid, desc)
                          ).pack(side="left", padx=2)

    def _delete(self, gasto_id: int, desc: str):
        if messagebox.askyesno("Confirmar eliminación",
                               f"¿Eliminar el gasto «{desc}»?\nEsta acción no se puede deshacer."):
            self.db.delete_gasto(gasto_id)
            self._apply_filters()
