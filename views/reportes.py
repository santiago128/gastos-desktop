from __future__ import annotations
import customtkinter as ctk
from datetime import date
from typing import Callable
import io
import csv
import os

from db import Database
from utils import format_currency, periodo_label, ultimos_n_meses, mes_actual_periodo

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


_DARK_BG   = "#1c1c1c"
_LIGHT_BG  = "#f0f0f0"
_GRID_D    = "#333333"
_GRID_L    = "#dddddd"
_TEXT_D    = "#cccccc"
_TEXT_L    = "#333333"


def _mpl_theme(dark: bool):
    bg   = _DARK_BG  if dark else _LIGHT_BG
    grid = _GRID_D   if dark else _GRID_L
    txt  = _TEXT_D   if dark else _TEXT_L
    plt.rcParams.update({
        'figure.facecolor':  bg,
        'axes.facecolor':    bg,
        'axes.edgecolor':    grid,
        'axes.labelcolor':   txt,
        'text.color':        txt,
        'xtick.color':       txt,
        'ytick.color':       txt,
        'grid.color':        grid,
    })
    return bg, txt


class ReportesView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._canvases: list = []
        self._build()

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Reportes", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w")

        # Month picker for category chart
        today = date.today()
        months = [f"{m:02d}" for m in range(1, 13)]
        years  = [str(y) for y in range(today.year - 2, today.year + 1)]
        self.sel_month = ctk.StringVar(value=f"{today.month:02d}")
        self.sel_year  = ctk.StringVar(value=str(today.year))

        ctrl = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl.grid(row=0, column=2, sticky="e")
        ctk.CTkLabel(ctrl, text="Mes:").pack(side="left", padx=4)
        ctk.CTkComboBox(ctrl, values=months, variable=self.sel_month, width=70,
                        command=lambda _: self.refresh()).pack(side="left", padx=2)
        ctk.CTkComboBox(ctrl, values=years, variable=self.sel_year, width=85,
                        command=lambda _: self.refresh()).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="Exportar CSV", width=110, height=30,
                      command=self._export_csv).pack(side="left", padx=(10, 0))

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, sticky="nsew")

        self._tab_bar   = tabs.add("Barras mensuales")
        self._tab_pie   = tabs.add("Por categoría")
        self._tab_trend = tabs.add("Tendencia anual")
        self._tab_comp  = tabs.add("Comparativo")

        for t in [self._tab_bar, self._tab_pie, self._tab_trend, self._tab_comp]:
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(0, weight=1)

    # ─────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────

    def refresh(self, **_):
        # Destroy previous canvas widgets
        for c in self._canvases:
            try:
                c.get_tk_widget().destroy()
            except Exception:
                pass
        self._canvases.clear()

        if not HAS_MPL:
            for tab in [self._tab_bar, self._tab_pie, self._tab_trend, self._tab_comp]:
                ctk.CTkLabel(tab,
                             text="matplotlib no está instalado.\nEjecuta: pip install matplotlib",
                             text_color="gray").grid(row=0, column=0, pady=40)
            return

        dark = ctk.get_appearance_mode().lower() == "dark"
        bg, _ = _mpl_theme(dark)
        moneda = self.db.get_config('moneda', 'COP')
        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())

        self._draw_monthly_bars(self._tab_bar, moneda, dark, bg)
        self._draw_category_pie(self._tab_pie, year, month, moneda, dark, bg)
        self._draw_trend(self._tab_trend, moneda, dark, bg)
        self._draw_comparison(self._tab_comp, moneda, dark, bg)

    # ─────────────────────────────────────────
    # Charts
    # ─────────────────────────────────────────

    def _embed(self, fig: Figure, parent):
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        w = canvas.get_tk_widget()
        w.grid(row=0, column=0, sticky="nsew")
        self._canvases.append(canvas)
        return canvas

    def _draw_monthly_bars(self, parent, moneda, dark, bg):
        data   = self.db.get_totales_por_mes(6)
        labels = [periodo_label(d['periodo']) for d in data]
        totals = [d['total'] for d in data]

        fig, ax = plt.subplots(figsize=(9, 4.5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        bars = ax.bar(labels, totals, color='#2196F3', alpha=0.85)
        ax.bar_label(bars,
                     labels=[format_currency(v, moneda, short=True) for v in totals],
                     padding=4, fontsize=9)
        ax.set_title("Gastos últimos 6 meses", fontsize=13)
        ax.set_ylabel(f"Monto ({moneda})")
        ax.grid(axis='y', linestyle='--', alpha=0.4)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()
        self._embed(fig, parent)

    def _draw_category_pie(self, parent, year, month, moneda, dark, bg):
        data = self.db.get_totales_por_categoria_mes(year, month)
        if not data:
            ctk.CTkLabel(parent, text="Sin datos para el mes seleccionado.",
                         text_color="gray").grid(row=0, column=0, pady=40)
            return

        labels  = [d['nombre'] for d in data]
        values  = [d['total']  for d in data]
        colors  = [d['color']  for d in data]

        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        wedges, texts, autotexts = ax.pie(
            values, labels=None, colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            startangle=90, pctdistance=0.8,
            wedgeprops=dict(width=0.55, edgecolor=bg, linewidth=2),
        )
        for at in autotexts:
            at.set_fontsize(9)
        ax.legend(wedges, [f"{l}: {format_currency(v, moneda, short=True)}"
                           for l, v in zip(labels, values)],
                  loc="center left", bbox_to_anchor=(1, 0.5), fontsize=9)
        meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        ax.set_title(f"Distribución por categoría — {meses[month-1]} {year}", fontsize=13)
        fig.tight_layout()
        self._embed(fig, parent)

    def _draw_trend(self, parent, moneda, dark, bg):
        data   = self.db.get_totales_por_mes(12)
        labels = [periodo_label(d['periodo']) for d in data]
        totals = [d['total'] for d in data]

        fig, ax = plt.subplots(figsize=(9, 4.5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        ax.plot(labels, totals, marker='o', color='#4CAF50', linewidth=2, markersize=5)
        ax.fill_between(range(len(labels)), totals, alpha=0.15, color='#4CAF50')
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
        ax.set_title("Tendencia de gasto mensual (12 meses)", fontsize=13)
        ax.set_ylabel(f"Monto ({moneda})")
        ax.grid(linestyle='--', alpha=0.4)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()
        self._embed(fig, parent)

    def _draw_comparison(self, parent, moneda, dark, bg):
        import numpy as np
        from utils import ultimos_n_meses
        import calendar as _cal

        periodos = ultimos_n_meses(3)
        cats_data = {}
        for p in periodos:
            y, m = map(int, p.split('-'))
            totals = self.db.get_totales_por_categoria_mes(y, m)
            for d in totals:
                cats_data.setdefault(d['nombre'], {'color': d['color'], 'totals': []})
                cats_data[d['nombre']]['totals'].append(d['total'])

        # Pad missing months
        for k, v in cats_data.items():
            while len(v['totals']) < len(periodos):
                v['totals'].insert(0, 0)

        # Keep top 7 categories by total
        sorted_cats = sorted(cats_data.items(), key=lambda x: sum(x[1]['totals']), reverse=True)[:7]
        if not sorted_cats:
            ctk.CTkLabel(parent, text="Sin datos suficientes.", text_color="gray").grid(
                row=0, column=0, pady=40)
            return

        labels = [periodo_label(p) for p in periodos]
        x      = np.arange(len(labels))
        n      = len(sorted_cats)
        width  = 0.8 / n

        fig, ax = plt.subplots(figsize=(9, 4.5))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        for i, (cat, info) in enumerate(sorted_cats):
            offset = (i - n / 2 + 0.5) * width
            ax.bar(x + offset, info['totals'], width, label=cat,
                   color=info['color'], alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_title("Comparativo por categoría (últimos 3 meses)", fontsize=13)
        ax.set_ylabel(f"Monto ({moneda})")
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(axis='y', linestyle='--', alpha=0.4)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()
        self._embed(fig, parent)

    # ─────────────────────────────────────────
    # Export
    # ─────────────────────────────────────────

    def _export_csv(self):
        from tkinter import filedialog
        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        gastos = self.db.get_gastos(
            fecha_desde=f"{year}-{month:02d}-01",
            fecha_hasta=f"{year}-{month:02d}-{last:02d}",
        )
        if not gastos:
            from tkinter import messagebox
            messagebox.showinfo("Sin datos", "No hay gastos en el período seleccionado.")
            return

        meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        default_name = f"gastos_{meses[month-1]}_{year}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not path:
            return

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['Fecha', 'Descripción', 'Categoría', 'Método de pago',
                             'Tarjeta', 'Monto', 'Corte', 'Notas'])
            for g in gastos:
                writer.writerow([
                    g.fecha, g.descripcion,
                    g.categoria_nombre or '',
                    g.metodo_pago,
                    g.tarjeta_nombre or '',
                    g.monto,
                    g.corte_periodo or '',
                    g.notas,
                ])

        from tkinter import messagebox
        messagebox.showinfo("Exportado", f"Archivo guardado en:\n{path}")
