from __future__ import annotations
import calendar
import csv
from datetime import date
from typing import Callable, Optional, List, Dict

import customtkinter as ctk

from db import Database
from utils import format_currency, format_date, periodo_label, ultimos_n_meses

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_pdf import PdfPages
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ── Color constants ──────────────────────────────────────────────────────────
_ACCENT      = "#2196F3"
_ACCENT_DIM  = "#1565C0"
_GREEN       = "#4CAF50"
_RED         = "#F44336"
_ORANGE      = "#FF9800"

_DARK_BG     = "#1e1e1e"
_LIGHT_BG    = "#f5f5f5"
_DARK_PANEL  = "#2a2a2a"
_LIGHT_PANEL = "#e8e8e8"
_DARK_GRID   = "#383838"
_LIGHT_GRID  = "#cccccc"
_DARK_TEXT   = "#d4d4d4"
_LIGHT_TEXT  = "#1a1a1a"


def _setup_mpl_theme(dark: bool) -> dict:
    bg    = _DARK_BG    if dark else _LIGHT_BG
    panel = _DARK_PANEL if dark else _LIGHT_PANEL
    grid  = _DARK_GRID  if dark else _LIGHT_GRID
    txt   = _DARK_TEXT  if dark else _LIGHT_TEXT
    plt.rcParams.update({
        'figure.facecolor':  bg,
        'axes.facecolor':    bg,
        'axes.edgecolor':    grid,
        'axes.labelcolor':   txt,
        'text.color':        txt,
        'xtick.color':       txt,
        'ytick.color':       txt,
        'grid.color':        grid,
        'legend.facecolor':  panel,
        'legend.edgecolor':  grid,
        'legend.labelcolor': txt,
    })
    return {'bg': bg, 'panel': panel, 'grid': grid, 'txt': txt}


# ─────────────────────────────────────────────────────────────────────────────
# Main view
# ─────────────────────────────────────────────────────────────────────────────

class ReportesView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db       = db
        self.navigate = navigate

        # ── Interactive state ────────────────────────────────────────────────
        self._dark: bool = True
        self._colors: dict = {}
        self._moneda: str = 'COP'

        self._selected_period:   Optional[str] = None   # "YYYY-MM"
        self._selected_category: Optional[str] = None   # category name

        # bar chart
        self._bar_periods:  List[str] = []
        self._bars:         list      = []
        # pie chart
        self._wedges:          list      = []
        self._pie_cat_names:   List[str] = []
        self._pie_cat_colors:  List[str] = []
        self._pie_cat_totals:  List[float] = []
        self._pie_cat_ids:     List[Optional[int]] = []

        # matplotlib objects
        self._fig_main:     Optional[Figure]            = None
        self._ax_bar:       Optional[plt.Axes]          = None
        self._ax_pie:       Optional[plt.Axes]          = None
        self._canvas_main:  Optional[FigureCanvasTkAgg] = None
        self._aux_canvases: List[FigureCanvasTkAgg]     = []

        self._build()

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Reportes",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w")

        today  = date.today()
        months = [f"{m:02d}" for m in range(1, 13)]
        years  = [str(y) for y in range(today.year - 2, today.year + 1)]
        self.sel_month = ctk.StringVar(value=f"{today.month:02d}")
        self.sel_year  = ctk.StringVar(value=str(today.year))

        ctrl = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl.grid(row=0, column=2, sticky="e")
        ctk.CTkLabel(ctrl, text="Mes:").pack(side="left", padx=4)
        ctk.CTkComboBox(ctrl, values=months, variable=self.sel_month, width=70,
                        command=lambda _: self._on_month_picker_change()).pack(side="left", padx=2)
        ctk.CTkComboBox(ctrl, values=years, variable=self.sel_year, width=85,
                        command=lambda _: self._on_month_picker_change()).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="📄 PDF", width=90, height=30,
                      fg_color=_RED, hover_color="#B71C1C",
                      command=self._export_pdf).pack(side="left", padx=(12, 4))
        ctk.CTkButton(ctrl, text="📊 CSV", width=90, height=30,
                      command=self._export_csv).pack(side="left", padx=4)

        # ── Tabs ──
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew")

        self._tab_main  = self.tabs.add("📊  Barras + Torta")
        self._tab_trend = self.tabs.add("📈  Tendencia")
        self._tab_comp  = self.tabs.add("📉  Comparativo")

        # Interactive tab: charts (row 0) + detail panel (row 1)
        self._tab_main.grid_columnconfigure(0, weight=1)
        self._tab_main.grid_rowconfigure(0, weight=3)
        self._tab_main.grid_rowconfigure(1, weight=2)

        for t in [self._tab_trend, self._tab_comp]:
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(0, weight=1)

        self._build_detail_panel()

    def _build_detail_panel(self):
        self._detail_outer = ctk.CTkFrame(
            self._tab_main, fg_color=("gray88", "gray18"), corner_radius=8
        )
        self._detail_outer.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self._detail_outer.grid_columnconfigure(0, weight=1)
        self._detail_outer.grid_rowconfigure(1, weight=1)

        self._detail_title = ctk.CTkLabel(
            self._detail_outer,
            text="⬆  Haz clic en una barra para seleccionar el mes · "
                 "luego clic en un segmento de la torta para ver el detalle",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self._detail_title.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 2))

        self._detail_scroll = ctk.CTkScrollableFrame(
            self._detail_outer, fg_color="transparent", height=120
        )
        self._detail_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 6))
        self._detail_scroll.grid_columnconfigure(0, weight=1)

    # ─────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────

    def refresh(self, **_):
        self._dark   = ctk.get_appearance_mode().lower() == "dark"
        self._colors = _setup_mpl_theme(self._dark)
        self._moneda = self.db.get_config('moneda', 'COP')

        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        self._selected_period   = f"{year}-{month:02d}"
        self._selected_category = None

        self._draw_main_chart()
        self._draw_trend_tab()
        self._draw_comparison_tab()

    # ─────────────────────────────────────────
    # Month picker change (no full redraw)
    # ─────────────────────────────────────────

    def _on_month_picker_change(self):
        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        new_period = f"{year}-{month:02d}"

        if self._fig_main and self._ax_pie and new_period != self._selected_period:
            self._selected_period   = new_period
            self._selected_category = None
            self._highlight_bars()
            self._redraw_pie()
            self._update_detail()
        elif not self._fig_main:
            self.refresh()

    # ─────────────────────────────────────────
    # Main interactive chart (bar + donut)
    # ─────────────────────────────────────────

    def _draw_main_chart(self):
        # Destroy old main canvas
        if self._canvas_main:
            try:
                self._canvas_main.get_tk_widget().destroy()
            except Exception:
                pass
            self._canvas_main = None
        if self._fig_main:
            plt.close(self._fig_main)
            self._fig_main = None

        c  = self._colors
        bg = c['bg']
        txt = c['txt']

        bar_data       = self.db.get_totales_por_mes(6)
        self._bar_periods = [d['periodo'] for d in bar_data]
        bar_labels        = [periodo_label(p) for p in self._bar_periods]
        bar_totals        = [d['total']   for d in bar_data]

        # Ensure selected period is in the data
        if self._selected_period not in self._bar_periods and self._bar_periods:
            self._selected_period = self._bar_periods[-1]

        # Create figure with two subplots side-by-side
        self._fig_main = plt.figure(figsize=(13, 4.0), facecolor=bg)
        gs = self._fig_main.add_gridspec(
            1, 2, width_ratios=[1.35, 1],
            wspace=0.28, left=0.06, right=0.97, top=0.87, bottom=0.16
        )
        self._ax_bar = self._fig_main.add_subplot(gs[0])
        self._ax_pie = self._fig_main.add_subplot(gs[1])

        # ── Bar chart ──
        self._bars = []
        for i, (lbl, total) in enumerate(zip(bar_labels, bar_totals)):
            selected = (self._bar_periods[i] == self._selected_period)
            bar = self._ax_bar.bar(
                lbl, total,
                color=_ACCENT if selected else _ACCENT_DIM,
                alpha=1.0   if selected else 0.50,
                linewidth=0,
                picker=True,
            )[0]
            self._bars.append(bar)

        self._ax_bar.bar_label(
            self._ax_bar.containers[0],
            labels=[format_currency(v, self._moneda, short=True) for v in bar_totals],
            padding=3, fontsize=8, color=txt,
        )
        self._ax_bar.set_title(
            "Gastos últimos 6 meses  ·  clic en barra = seleccionar mes",
            fontsize=10, color=txt,
        )
        self._ax_bar.set_ylabel(f"Monto ({self._moneda})", fontsize=9)
        self._ax_bar.grid(axis='y', linestyle='--', alpha=0.35)
        self._ax_bar.spines[['top', 'right']].set_visible(False)
        self._ax_bar.tick_params(labelsize=8)

        # ── Donut chart (initial draw) ──
        self._draw_pie_on_ax()

        # ── Embed canvas ──
        self._canvas_main = FigureCanvasTkAgg(self._fig_main, master=self._tab_main)
        self._canvas_main.draw()
        self._canvas_main.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # ── Event connections ──
        self._fig_main.canvas.mpl_connect(
            'button_press_event', self._on_main_click
        )
        self._fig_main.canvas.mpl_connect(
            'motion_notify_event', self._on_main_hover
        )

        self._update_detail()

    def _draw_pie_on_ax(self):
        """(Re)draw the donut chart on self._ax_pie. Called after bar click."""
        ax  = self._ax_pie
        c   = self._colors
        bg  = c['bg']
        txt = c['txt']

        ax.clear()
        self._wedges         = []
        self._pie_cat_names  = []
        self._pie_cat_colors = []
        self._pie_cat_totals = []
        self._pie_cat_ids    = []

        if not self._selected_period:
            ax.text(0.5, 0.5, "Sin datos", ha='center', va='center', color=txt)
            return

        year, month = map(int, self._selected_period.split('-'))
        MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        label_period = f"{MESES[month-1]} {year}"

        data = self.db.get_totales_por_categoria_mes(year, month)
        if not data:
            ax.text(0.5, 0.5, f"Sin datos\n{label_period}",
                    ha='center', va='center', color=txt, fontsize=11)
            ax.set_title(f"Distribución — {label_period}", fontsize=10, color=txt)
            return

        self._pie_cat_names  = [d['nombre'] for d in data]
        self._pie_cat_colors = [d['color']  for d in data]
        self._pie_cat_totals = [d['total']  for d in data]
        values = self._pie_cat_totals
        total  = sum(values)

        explode = [
            0.08 if n == self._selected_category else 0.0
            for n in self._pie_cat_names
        ]

        wedges, _, autotexts = ax.pie(
            values,
            labels=None,
            colors=self._pie_cat_colors,
            autopct=lambda p: f'{p:.1f}%' if p > 4.5 else '',
            startangle=90,
            pctdistance=0.76,
            explode=explode,
            wedgeprops=dict(width=0.52, edgecolor=bg, linewidth=2, picker=True),
        )
        self._wedges = wedges

        # Highlight selected wedge border
        for w, name in zip(wedges, self._pie_cat_names):
            if name == self._selected_category:
                w.set_linewidth(3)
                w.set_edgecolor(_ACCENT)

        for at in autotexts:
            at.set_fontsize(8)
            at.set_color(txt)

        # Center total
        ax.text(0, 0, format_currency(total, self._moneda, short=True),
                ha='center', va='center',
                fontsize=10, fontweight='bold', color=txt)

        # Compact legend (top 6)
        patches = [
            mpatches.Patch(
                color=d['color'],
                label=f"{d['nombre'][:13]}: {format_currency(d['total'], self._moneda, short=True)}"
            )
            for d in data[:6]
        ]
        ax.legend(handles=patches, loc='lower center',
                  bbox_to_anchor=(0.5, -0.26),
                  ncol=2, fontsize=7.5, framealpha=0.25)

        click_hint = "  ·  clic en segmento = ver detalle" if not self._selected_category else \
                     f"  ·  seleccionada: {self._selected_category}"
        ax.set_title(f"Distribución — {label_period}{click_hint}",
                     fontsize=9.5, color=txt)

    # ─────────────────────────────────────────
    # Interaction handlers
    # ─────────────────────────────────────────

    def _on_main_click(self, event):
        if event.inaxes == self._ax_bar:
            self._handle_bar_click(event)
        elif event.inaxes == self._ax_pie:
            self._handle_pie_click(event)

    def _handle_bar_click(self, event):
        for i, bar in enumerate(self._bars):
            if bar.contains(event)[0]:
                period = self._bar_periods[i]
                if period == self._selected_period:
                    return
                self._selected_period   = period
                self._selected_category = None
                # Sync picker dropdowns
                y, m = map(int, period.split('-'))
                self.sel_year.set(str(y))
                self.sel_month.set(f"{m:02d}")
                self._highlight_bars()
                self._redraw_pie()
                self._update_detail()
                return

    def _handle_pie_click(self, event):
        for i, wedge in enumerate(self._wedges):
            if wedge.contains(event)[0]:
                name = self._pie_cat_names[i]
                # Toggle selection
                self._selected_category = None if name == self._selected_category else name
                self._redraw_pie()
                self._update_detail()
                return

    def _on_main_hover(self, event):
        if not self._fig_main:
            return
        changed = False

        # Bar hover
        if event.inaxes == self._ax_bar:
            for i, bar in enumerate(self._bars):
                hovered  = bar.contains(event)[0]
                selected = (self._bar_periods[i] == self._selected_period)
                target_alpha = 1.0 if (selected or hovered) else 0.50
                target_color = _ACCENT if (selected or hovered) else _ACCENT_DIM
                if abs(bar.get_alpha() - target_alpha) > 0.01:
                    bar.set_alpha(target_alpha)
                    bar.set_facecolor(target_color)
                    changed = True
        else:
            # Reset non-selected bars to dim
            for i, bar in enumerate(self._bars):
                selected = (self._bar_periods[i] == self._selected_period)
                ta = 1.0 if selected else 0.50
                tc = _ACCENT if selected else _ACCENT_DIM
                if abs(bar.get_alpha() - ta) > 0.01:
                    bar.set_alpha(ta)
                    bar.set_facecolor(tc)
                    changed = True

        # Pie hover — slight scale on hovered wedge
        if event.inaxes == self._ax_pie and self._wedges:
            for i, wedge in enumerate(self._wedges):
                hovered  = wedge.contains(event)[0]
                selected = (self._pie_cat_names[i] == self._selected_category
                            if i < len(self._pie_cat_names) else False)
                target_r = 1.08 if hovered else (1.0 if not selected else 1.0)
                if abs(wedge.get_radius() - target_r) > 0.005:
                    wedge.set_radius(target_r)
                    changed = True

        if changed:
            self._fig_main.canvas.draw_idle()

    def _highlight_bars(self):
        for i, bar in enumerate(self._bars):
            sel = (self._bar_periods[i] == self._selected_period)
            bar.set_alpha(1.0 if sel else 0.50)
            bar.set_facecolor(_ACCENT if sel else _ACCENT_DIM)
        if self._fig_main:
            self._fig_main.canvas.draw_idle()

    def _redraw_pie(self):
        self._draw_pie_on_ax()
        if self._fig_main:
            self._fig_main.canvas.draw_idle()

    # ─────────────────────────────────────────
    # Detail panel
    # ─────────────────────────────────────────

    def _update_detail(self):
        for w in self._detail_scroll.winfo_children():
            w.destroy()

        if not self._selected_period:
            return

        year, month = map(int, self._selected_period.split('-'))
        MESES_LONG = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                      'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        last_day = calendar.monthrange(year, month)[1]
        all_gastos = self.db.get_gastos(
            fecha_desde=f"{year}-{month:02d}-01",
            fecha_hasta=f"{year}-{month:02d}-{last_day:02d}",
        )

        if self._selected_category:
            gastos = [g for g in all_gastos
                      if (g.categoria_nombre or 'Sin categoría') == self._selected_category]
            total_cat = sum(g.monto for g in gastos)
            cat_color = next(
                (c for n, c in zip(self._pie_cat_names, self._pie_cat_colors)
                 if n == self._selected_category),
                '#607D8B',
            )
            self._detail_title.configure(
                text=f"● {self._selected_category}  ·  {MESES_LONG[month-1]} {year}  ·  "
                     f"{len(gastos)} gastos  ·  {format_currency(total_cat, self._moneda)}  "
                     f"  —  clic nuevamente en el segmento para deseleccionar",
                text_color=cat_color,
            )
            self._render_expense_rows(gastos)
        else:
            total = sum(g.monto for g in all_gastos)
            self._detail_title.configure(
                text=f"{MESES_LONG[month-1]} {year}  ·  {len(all_gastos)} gastos  ·  "
                     f"Total: {format_currency(total, self._moneda)}  "
                     f"  —  Haz clic en un segmento de la torta para ver el detalle",
                text_color=("gray20", "gray70"),
            )
            # Mini category summary
            if self._pie_cat_totals and total > 0:
                for name, color, cat_total in zip(
                    self._pie_cat_names, self._pie_cat_colors, self._pie_cat_totals
                ):
                    row_f = ctk.CTkFrame(self._detail_scroll, fg_color="transparent",
                                         corner_radius=4)
                    row_f.pack(fill="x", pady=1, padx=4)
                    ctk.CTkLabel(row_f, text="●", text_color=color,
                                 font=ctk.CTkFont(size=13), width=22).pack(side="left", padx=(6, 2))
                    ctk.CTkLabel(row_f, text=name,
                                 font=ctk.CTkFont(size=12), anchor="w").pack(
                        side="left", fill="x", expand=True)
                    pct = cat_total / total * 100
                    ctk.CTkLabel(
                        row_f,
                        text=f"{format_currency(cat_total, self._moneda)}  ({pct:.1f}%)",
                        font=ctk.CTkFont(size=12),
                        text_color=_RED,
                    ).pack(side="right", padx=10)

    def _render_expense_rows(self, gastos):
        self._detail_scroll.grid_columnconfigure(0, weight=1)
        for i, g in enumerate(gastos):
            bg = ("gray90", "gray20") if i % 2 == 0 else ("gray86", "gray17")
            row_f = ctk.CTkFrame(self._detail_scroll, fg_color=bg, corner_radius=4)
            row_f.pack(fill="x", pady=1, padx=2)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=format_date(g.fecha),
                         width=84, font=ctk.CTkFont(size=11),
                         text_color="gray").grid(row=0, column=0, padx=(8, 4), pady=5)
            ctk.CTkLabel(row_f, text=g.descripcion, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(
                row=0, column=1, sticky="ew", padx=4, pady=5)
            ctk.CTkLabel(row_f, text=g.metodo_pago,
                         font=ctk.CTkFont(size=11), text_color="gray",
                         width=170).grid(row=0, column=2, padx=4, pady=5)
            if g.notas:
                ctk.CTkLabel(row_f, text=f"📝 {g.notas}",
                             font=ctk.CTkFont(size=10), text_color="gray",
                             anchor="w").grid(row=0, column=3, padx=4, pady=5)
            ctk.CTkLabel(
                row_f,
                text=format_currency(g.monto, self._moneda),
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_RED, width=120,
            ).grid(row=0, column=4, padx=(4, 10), pady=5)

    # ─────────────────────────────────────────
    # Trend tab
    # ─────────────────────────────────────────

    def _draw_trend_tab(self):
        self._destroy_aux_canvases(self._tab_trend)
        c  = self._colors
        bg = c['bg']
        txt = c['txt']

        data   = self.db.get_totales_por_mes(12)
        labels = [periodo_label(d['periodo']) for d in data]
        totals = [d['total'] for d in data]

        fig, ax = plt.subplots(figsize=(10, 4.6))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        line, = ax.plot(labels, totals, marker='o', color=_GREEN, linewidth=2.5,
                        markersize=7, markerfacecolor=_GREEN,
                        markeredgecolor=bg, markeredgewidth=2, picker=6)
        ax.fill_between(range(len(labels)), totals, alpha=0.11, color=_GREEN)

        for i, v in enumerate(totals):
            ax.annotate(
                format_currency(v, self._moneda, short=True),
                (i, v), textcoords="offset points", xytext=(0, 11),
                ha='center', fontsize=8, color=txt, alpha=0.85,
            )

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=28, ha='right', fontsize=9)
        ax.set_title("Tendencia de gasto mensual — últimos 12 meses", fontsize=12, color=txt)
        ax.set_ylabel(f"Monto ({self._moneda})", fontsize=10)
        ax.grid(linestyle='--', alpha=0.33)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._tab_trend)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._aux_canvases.append(canvas)

        # Hover tooltip
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=c['panel'], ec=_GREEN, lw=1.5),
            fontsize=9, color=txt, visible=False,
        )

        def _hover(event):
            if event.inaxes != ax:
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
                return
            cont, ind = line.contains(event)
            if cont:
                idx = ind['ind'][0]
                annot.xy = (idx, totals[idx])
                annot.set_text(f"{labels[idx]}\n{format_currency(totals[idx], self._moneda)}")
                annot.set_visible(True)
                canvas.draw_idle()
            elif annot.get_visible():
                annot.set_visible(False)
                canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', _hover)

    # ─────────────────────────────────────────
    # Comparison tab
    # ─────────────────────────────────────────

    def _draw_comparison_tab(self):
        self._destroy_aux_canvases(self._tab_comp)
        c   = self._colors
        bg  = c['bg']
        txt = c['txt']

        periodos  = ultimos_n_meses(3)
        cats_data: Dict[str, dict] = {}

        for p in periodos:
            y_p, m_p = map(int, p.split('-'))
            for d in self.db.get_totales_por_categoria_mes(y_p, m_p):
                cats_data.setdefault(d['nombre'], {'color': d['color'], 'values': {}})
                cats_data[d['nombre']]['values'][p] = d['total']

        sorted_cats = sorted(
            cats_data.items(),
            key=lambda x: sum(x[1]['values'].values()),
            reverse=True,
        )[:7]

        if not sorted_cats:
            ctk.CTkLabel(self._tab_comp, text="Sin datos suficientes.",
                         text_color="gray").grid(row=0, column=0, pady=40)
            return

        labels = [periodo_label(p) for p in periodos]
        x      = np.arange(len(labels))
        n      = len(sorted_cats)
        width  = 0.78 / n

        fig, ax = plt.subplots(figsize=(10, 4.8))
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        bar_containers = []
        for i, (cat, info) in enumerate(sorted_cats):
            vals   = [info['values'].get(p, 0) for p in periodos]
            offset = (i - n / 2 + 0.5) * width
            bars   = ax.bar(x + offset, vals, width, label=cat,
                            color=info['color'], alpha=0.85, picker=True)
            bar_containers.append((cat, bars, vals))

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_title(
            "Comparativo por categoría — últimos 3 meses  ·  hover para ver valor",
            fontsize=11, color=txt,
        )
        ax.set_ylabel(f"Monto ({self._moneda})", fontsize=10)
        ax.legend(fontsize=8.5, loc='upper right')
        ax.grid(axis='y', linestyle='--', alpha=0.33)
        ax.spines[['top', 'right']].set_visible(False)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._tab_comp)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._aux_canvases.append(canvas)

        # Hover tooltip
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(8, 8), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=c['panel'], ec=_ACCENT, lw=1.5),
            fontsize=9, color=txt, visible=False,
        )

        def _hover(event):
            if event.inaxes != ax:
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
                return
            for cat_name, bars, vals in bar_containers:
                for j, bar in enumerate(bars):
                    if bar.contains(event)[0]:
                        annot.xy = (bar.get_x() + bar.get_width() / 2, bar.get_height())
                        annot.set_text(
                            f"{cat_name}\n{labels[j]}\n{format_currency(vals[j], self._moneda)}"
                        )
                        annot.set_visible(True)
                        canvas.draw_idle()
                        return
            if annot.get_visible():
                annot.set_visible(False)
                canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', _hover)

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _destroy_aux_canvases(self, tab_widget):
        for w in tab_widget.winfo_children():
            w.destroy()
        # Close figures that belong to aux canvases to free memory
        keep = []
        for c in self._aux_canvases:
            try:
                if c.get_tk_widget().winfo_exists():
                    keep.append(c)
                else:
                    plt.close(c.figure)
            except Exception:
                pass
        self._aux_canvases = keep

    # ─────────────────────────────────────────
    # PDF Export (matplotlib PdfPages — no extra deps)
    # ─────────────────────────────────────────

    def _export_pdf(self):
        from tkinter import filedialog, messagebox

        if not HAS_MPL:
            messagebox.showerror("Error", "matplotlib no está instalado.")
            return

        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        MESES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                 'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        MESES_A = ['Ene','Feb','Mar','Abr','May','Jun',
                   'Jul','Ago','Sep','Oct','Nov','Dic']

        default_name = f"reporte_{MESES_A[month-1]}_{year}.pdf"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=default_name,
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
        )
        if not path:
            return

        moneda    = self.db.get_config('moneda', 'COP')
        nombre    = self.db.get_config('nombre_usuario', 'Usuario')
        presup    = float(self.db.get_config('presupuesto_mensual', '0') or '0')
        last_day  = calendar.monthrange(year, month)[1]
        gastos    = self.db.get_gastos(
            fecha_desde=f"{year}-{month:02d}-01",
            fecha_hasta=f"{year}-{month:02d}-{last_day:02d}",
        )
        total_mes = sum(g.monto for g in gastos)
        cat_data  = self.db.get_totales_por_categoria_mes(year, month)
        bar_data  = self.db.get_totales_por_mes(6)

        # PDF always uses white theme for readability
        PDF = {
            'bg':    '#ffffff', 'panel': '#f0f4ff',
            'grid':  '#dddddd', 'txt':   '#111111',
            'muted': '#666666',
        }
        plt.rcParams.update({
            'figure.facecolor':  PDF['bg'],
            'axes.facecolor':    PDF['bg'],
            'axes.edgecolor':    PDF['grid'],
            'axes.labelcolor':   PDF['txt'],
            'text.color':        PDF['txt'],
            'xtick.color':       PDF['txt'],
            'ytick.color':       PDF['txt'],
            'grid.color':        PDF['grid'],
            'legend.facecolor':  PDF['panel'],
            'legend.edgecolor':  PDF['grid'],
            'legend.labelcolor': PDF['txt'],
        })

        try:
            with PdfPages(path) as pdf:

                # ══════════════════════════════════════════════
                # PAGE 1 — Cover + category summary
                # ══════════════════════════════════════════════
                fig1 = plt.figure(figsize=(8.5, 11))
                fig1.patch.set_facecolor(PDF['bg'])
                ax1  = fig1.add_axes([0, 0, 1, 1])
                ax1.set_xlim(0, 1)
                ax1.set_ylim(0, 1)
                ax1.axis('off')

                # Header band
                ax1.add_patch(mpatches.FancyBboxPatch(
                    (0, 0.895), 1, 0.105,
                    boxstyle="square", facecolor=_ACCENT, edgecolor='none'
                ))
                ax1.text(0.5, 0.955, "REPORTE DE GASTOS", ha='center', va='center',
                         fontsize=24, fontweight='bold', color='white')
                ax1.text(0.5, 0.912, f"{MESES[month-1].upper()}  {year}",
                         ha='center', va='center', fontsize=14, color='#BBDEFB')

                # Subtitle line
                ax1.text(0.06, 0.875, f"Usuario: {nombre}", fontsize=11, color=PDF['txt'])
                ax1.text(0.06, 0.852,
                         f"Generado el {date.today().strftime('%d/%m/%Y')}  ·  "
                         f"GastosApp",
                         fontsize=9, color=PDF['muted'])

                # ── Metric cards ──
                pct    = total_mes / presup * 100 if presup > 0 else 0
                pct_c  = _GREEN if pct < 75 else _ORANGE if pct < 100 else _RED

                def _metric(x, y, w, h, title, value, color, note=''):
                    ax1.add_patch(mpatches.FancyBboxPatch(
                        (x, y), w, h,
                        boxstyle="round,pad=0.015",
                        facecolor=color, edgecolor='none', alpha=0.10
                    ))
                    ax1.add_patch(mpatches.Rectangle(
                        (x, y + h - 0.0055), w, 0.0055,
                        facecolor=color, edgecolor='none'
                    ))
                    ax1.text(x + w / 2, y + h - 0.022, title,
                             ha='center', va='top', fontsize=8.5, color=PDF['muted'])
                    ax1.text(x + w / 2, y + h / 2 - 0.005, value,
                             ha='center', va='center',
                             fontsize=13, fontweight='bold', color=color)
                    if note:
                        ax1.text(x + w / 2, y + 0.013, note,
                                 ha='center', va='bottom', fontsize=8, color=PDF['muted'])

                avg_gasto = total_mes / len(gastos) if gastos else 0
                _metric(0.04, 0.79, 0.28, 0.055, "Total gastado",
                        format_currency(total_mes, moneda), _RED)
                _metric(0.36, 0.79, 0.28, 0.055, "Transacciones",
                        str(len(gastos)), _ACCENT,
                        f"Promedio {format_currency(avg_gasto, moneda, short=True)}")
                if presup > 0:
                    _metric(0.68, 0.79, 0.28, 0.055, "Presupuesto usado",
                            f"{pct:.1f}%", pct_c,
                            f"de {format_currency(presup, moneda)}")
                else:
                    _metric(0.68, 0.79, 0.28, 0.055, "Categorías",
                            str(len(cat_data)), _GREEN)

                # ── Category table ──
                ax1.text(0.05, 0.774, "Distribución por categoría",
                         fontsize=12, fontweight='bold', color=PDF['txt'])
                ax1.plot([0.05, 0.95], [0.758, 0.758], color=PDF['grid'], lw=0.8)

                # Column headers
                y_pos = 0.740
                for label, x_pos in [("Categoría", 0.05), ("Monto", 0.55),
                                      ("% del total", 0.73), ("Barra", 0.85)]:
                    ax1.text(x_pos, y_pos, label, fontsize=8.5,
                             fontweight='bold', color=PDF['muted'])
                y_pos -= 0.020

                for d in cat_data[:16]:
                    pct_cat = d['total'] / total_mes * 100 if total_mes > 0 else 0
                    # Color dot
                    ax1.add_patch(mpatches.Circle(
                        (0.038, y_pos + 0.005), 0.005,
                        facecolor=d['color'], edgecolor='none'
                    ))
                    ax1.text(0.05, y_pos, d['nombre'][:22], fontsize=8.5, color=PDF['txt'])
                    ax1.text(0.55, y_pos, format_currency(d['total'], moneda),
                             fontsize=8.5, color=PDF['txt'])
                    ax1.text(0.73, y_pos, f"{pct_cat:.1f}%",
                             fontsize=8.5, color=PDF['muted'])
                    # Mini progress bar
                    bar_w = min(pct_cat / 100 * 0.09, 0.09)
                    ax1.add_patch(mpatches.Rectangle(
                        (0.85, y_pos + 0.001), bar_w, 0.009,
                        facecolor=d['color'], edgecolor='none', alpha=0.75
                    ))
                    y_pos -= 0.020
                    if y_pos < 0.07:
                        break

                # Footer
                ax1.plot([0.05, 0.95], [0.038, 0.038], color=PDF['grid'], lw=0.5)
                ax1.text(0.5, 0.022,
                         "GastosApp — Reporte generado automáticamente",
                         ha='center', fontsize=8, color='#aaaaaa')

                pdf.savefig(fig1, bbox_inches='tight')
                plt.close(fig1)

                # ══════════════════════════════════════════════
                # PAGE 2 — Bar chart (6 months) + Donut side by side
                # ══════════════════════════════════════════════
                fig2 = plt.figure(figsize=(11, 5.5))
                fig2.patch.set_facecolor(PDF['bg'])
                fig2.suptitle(
                    f"Análisis gráfico — {MESES[month-1]} {year}",
                    fontsize=14, fontweight='bold', color=PDF['txt'], y=0.98,
                )
                gs2 = fig2.add_gridspec(1, 2, width_ratios=[1.3, 1],
                                        wspace=0.28, left=0.06, right=0.97,
                                        top=0.90, bottom=0.14)
                ax_b2 = fig2.add_subplot(gs2[0])
                ax_p2 = fig2.add_subplot(gs2[1])

                # Bar chart
                ax_b2.set_facecolor(PDF['bg'])
                b_labels = [periodo_label(d['periodo']) for d in bar_data]
                b_totals = [d['total'] for d in bar_data]
                b_colors = [_ACCENT if d['periodo'] == f"{year}-{month:02d}"
                            else '#90CAF9' for d in bar_data]
                bp = ax_b2.bar(b_labels, b_totals, color=b_colors, alpha=0.92, linewidth=0)
                ax_b2.bar_label(bp,
                                labels=[format_currency(v, moneda, short=True) for v in b_totals],
                                padding=3, fontsize=7.5)
                ax_b2.set_title("Gastos últimos 6 meses\n(barra azul = mes del reporte)",
                                fontsize=10)
                ax_b2.set_ylabel(f"Monto ({moneda})", fontsize=9)
                ax_b2.grid(axis='y', linestyle='--', alpha=0.4)
                ax_b2.spines[['top', 'right']].set_visible(False)
                ax_b2.tick_params(axis='x', labelsize=8, rotation=25)

                # Donut chart
                ax_p2.set_facecolor(PDF['bg'])
                if cat_data:
                    vals  = [d['total'] for d in cat_data]
                    clrs  = [d['color']  for d in cat_data]
                    nms   = [d['nombre'] for d in cat_data]
                    w2, _, at2 = ax_p2.pie(
                        vals, colors=clrs,
                        autopct=lambda p: f'{p:.1f}%' if p > 5 else '',
                        startangle=90, pctdistance=0.76,
                        wedgeprops=dict(width=0.52, edgecolor=PDF['bg'], linewidth=1.5),
                    )
                    for at in at2:
                        at.set_fontsize(7.5)
                    ax_p2.legend(
                        w2,
                        [f"{n[:12]}: {format_currency(v, moneda, short=True)}"
                         for n, v in zip(nms, vals)],
                        loc='lower center', bbox_to_anchor=(0.5, -0.30),
                        ncol=2, fontsize=7, framealpha=0.5,
                    )
                    ax_p2.text(0, 0, format_currency(total_mes, moneda, short=True),
                               ha='center', va='center',
                               fontsize=10, fontweight='bold', color=PDF['txt'])
                ax_p2.set_title(f"Distribución por categoría\n{MESES[month-1]} {year}",
                                fontsize=10)

                pdf.savefig(fig2, bbox_inches='tight')
                plt.close(fig2)

                # ══════════════════════════════════════════════
                # PAGE 3 — Trend chart (12 months)
                # ══════════════════════════════════════════════
                fig3, ax3 = plt.subplots(figsize=(11, 4.8))
                fig3.patch.set_facecolor(PDF['bg'])
                ax3.set_facecolor(PDF['bg'])

                t_data   = self.db.get_totales_por_mes(12)
                t_labels = [periodo_label(d['periodo']) for d in t_data]
                t_totals = [d['total'] for d in t_data]

                ax3.plot(t_labels, t_totals, marker='o', color=_GREEN,
                         linewidth=2.5, markersize=7,
                         markerfacecolor=_GREEN, markeredgecolor=PDF['bg'], markeredgewidth=2)
                ax3.fill_between(range(len(t_labels)), t_totals, alpha=0.10, color=_GREEN)
                for i, v in enumerate(t_totals):
                    ax3.annotate(format_currency(v, moneda, short=True),
                                 (i, v), textcoords="offset points", xytext=(0, 9),
                                 ha='center', fontsize=7.5, color=PDF['muted'])
                ax3.set_xticks(range(len(t_labels)))
                ax3.set_xticklabels(t_labels, rotation=28, ha='right', fontsize=9)
                ax3.set_title("Tendencia de gasto mensual — últimos 12 meses",
                              fontsize=12, color=PDF['txt'])
                ax3.set_ylabel(f"Monto ({moneda})", fontsize=10)
                ax3.grid(linestyle='--', alpha=0.35)
                ax3.spines[['top', 'right']].set_visible(False)
                fig3.tight_layout()

                pdf.savefig(fig3, bbox_inches='tight')
                plt.close(fig3)

                # ══════════════════════════════════════════════
                # PAGE 4+ — Expense table (30 rows/page)
                # ══════════════════════════════════════════════
                PAGE_ROWS = 28
                pages     = max(1, (len(gastos) + PAGE_ROWS - 1) // PAGE_ROWS)

                for pg in range(pages):
                    chunk = gastos[pg * PAGE_ROWS:(pg + 1) * PAGE_ROWS]

                    fig_t, ax_t = plt.subplots(figsize=(11, 8.5))
                    fig_t.patch.set_facecolor(PDF['bg'])
                    ax_t.axis('off')

                    sfx = f"  (pág. {pg+1} / {pages})" if pages > 1 else ""
                    ax_t.set_title(
                        f"Detalle de gastos — {MESES[month-1]} {year}{sfx}",
                        fontsize=13, fontweight='bold', pad=14,
                    )

                    col_labels = ['Fecha', 'Descripción', 'Categoría', 'Método de pago', 'Monto']
                    col_widths = [0.10, 0.34, 0.18, 0.22, 0.13]

                    table_data  = []
                    row_colours = []
                    for i, g in enumerate(chunk):
                        table_data.append([
                            format_date(g.fecha),
                            (g.descripcion[:40] + '…') if len(g.descripcion) > 40 else g.descripcion,
                            g.categoria_nombre or '—',
                            g.metodo_pago,
                            format_currency(g.monto, moneda),
                        ])
                        stripe = '#F7F9FF' if i % 2 == 0 else '#FFFFFF'
                        row_colours.append([stripe] * 5)

                    # Totals row
                    table_data.append(
                        ['', f"TOTAL  ({len(gastos)} gastos)", '', '',
                         format_currency(total_mes, moneda)]
                    )
                    row_colours.append(['#E3F2FD'] * 5)

                    tbl = ax_t.table(
                        cellText=table_data,
                        colLabels=col_labels,
                        colWidths=col_widths,
                        cellLoc='left',
                        loc='center',
                        cellColours=row_colours,
                    )
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(8.5)
                    tbl.scale(1, 1.45)

                    for j in range(len(col_labels)):
                        cell = tbl[0, j]
                        cell.set_facecolor(_ACCENT)
                        cell.set_text_props(color='white', fontweight='bold')
                    for j in range(len(col_labels)):
                        tbl[len(table_data), j].set_text_props(fontweight='bold')

                    pdf.savefig(fig_t, bbox_inches='tight')
                    plt.close(fig_t)

                # PDF metadata
                d_meta = pdf.infodict()
                d_meta['Title']   = f'Reporte Gastos {MESES[month-1]} {year}'
                d_meta['Author']  = f'GastosApp — {nombre}'
                d_meta['Subject'] = 'Reporte personal de gastos'

        finally:
            # Always restore the app's theme after PDF generation
            _setup_mpl_theme(self._dark)

        messagebox.showinfo("PDF generado", f"Reporte guardado en:\n{path}")

    # ─────────────────────────────────────────
    # CSV Export
    # ─────────────────────────────────────────

    def _export_csv(self):
        from tkinter import filedialog, messagebox
        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        last  = calendar.monthrange(year, month)[1]
        gastos = self.db.get_gastos(
            fecha_desde=f"{year}-{month:02d}-01",
            fecha_hasta=f"{year}-{month:02d}-{last:02d}",
        )
        if not gastos:
            messagebox.showinfo("Sin datos", "No hay gastos en el período seleccionado.")
            return

        MESES_A = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        default_name = f"gastos_{MESES_A[month-1]}_{year}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name,
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
                    g.fecha, g.descripcion, g.categoria_nombre or '',
                    g.metodo_pago, g.tarjeta_nombre or '',
                    g.monto, g.corte_periodo or '', g.notas,
                ])

        messagebox.showinfo("Exportado", f"Archivo guardado en:\n{path}")
