"""
views/reportes.py — Reportes interactivos con gráficas enlazadas y exportación PDF.

Gráficas:
  • Barras mensuales  — clic en barra → selecciona mes → actualiza la torta
  • Torta/dona        — clic en segmento → filtra panel de detalle
  • Panel de detalle  — lista de gastos filtrada por mes+categoría
  • Tendencia anual   — línea con tooltip hover
  • Comparativo 3m    — barras agrupadas con tooltip hover

PDF generado con reportlab (pip install reportlab):
  Pág 1 Portada con métricas y tabla de categorías
  Pág 2 Gráficas (barras + dona side by side)
  Pág 3 Tendencia anual
  Pág 4+ Tabla detallada de gastos
"""

from __future__ import annotations

import calendar
import csv
import io
from datetime import date
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from db import Database
from utils import (format_currency, format_date, periodo_label,
                   ultimos_n_meses, convertir_a_cop)

# ── Matplotlib ───────────────────────────────────────────────────────────────
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

# ── ReportLab (PDF profesional) ───────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage, HRFlowable, PageBreak, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    HAS_RL = True
except ImportError:
    HAS_RL = False

# ── Palette ──────────────────────────────────────────────────────────────────
_BLUE    = "#2196F3"
_BLUE_D  = "#1565C0"
_GREEN   = "#4CAF50"
_RED     = "#F44336"
_ORANGE  = "#FF9800"

_D_BG    = "#1e1e1e"
_D_PANEL = "#262626"
_D_GRID  = "#383838"
_D_TXT   = "#d0d0d0"
_L_BG    = "#f5f5f5"
_L_PANEL = "#e6e6e6"
_L_GRID  = "#cccccc"
_L_TXT   = "#1a1a1a"


def _apply_mpl_theme(dark: bool) -> dict:
    bg    = _D_BG    if dark else _L_BG
    panel = _D_PANEL if dark else _L_PANEL
    grid  = _D_GRID  if dark else _L_GRID
    txt   = _D_TXT   if dark else _L_TXT
    plt.rcParams.update({
        "figure.facecolor":  bg,
        "axes.facecolor":    bg,
        "axes.edgecolor":    grid,
        "axes.labelcolor":   txt,
        "text.color":        txt,
        "xtick.color":       txt,
        "ytick.color":       txt,
        "grid.color":        grid,
        "legend.facecolor":  panel,
        "legend.edgecolor":  grid,
        "legend.labelcolor": txt,
    })
    return {"bg": bg, "panel": panel, "grid": grid, "txt": txt}


# ─────────────────────────────────────────────────────────────────────────────
# Main view
# ─────────────────────────────────────────────────────────────────────────────

class ReportesView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db       = db
        self.navigate = navigate

        # state
        self._dark:    bool = True
        self._colors:  dict = {}
        self._moneda:  str  = "COP"
        self._tasas:   dict = {}

        self._sel_period:   Optional[str] = None   # "YYYY-MM"
        self._sel_category: Optional[str] = None   # category name

        # bar data
        self._bar_periods: List[str] = []
        self._bars:        list      = []

        # pie data
        self._wedges:        list        = []
        self._pie_names:     List[str]   = []
        self._pie_colors:    List[str]   = []
        self._pie_totals:    List[float] = []
        self._pie_raw:       List[dict]  = []

        # matplotlib objects
        self._fig_main:   Optional[Figure]            = None
        self._ax_bar:     Optional[plt.Axes]          = None
        self._ax_pie:     Optional[plt.Axes]          = None
        self._canvas_main: Optional[FigureCanvasTkAgg] = None

        self._trend_fig:    Optional[Figure]            = None
        self._trend_canvas: Optional[FigureCanvasTkAgg] = None
        self._comp_fig:     Optional[Figure]            = None
        self._comp_canvas:  Optional[FigureCanvasTkAgg] = None

        self._build()

    # ─────────────────────────────────────────
    # Build layout
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
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
                        command=lambda _: self._on_picker_change()).pack(side="left", padx=2)
        ctk.CTkComboBox(ctrl, values=years, variable=self.sel_year, width=85,
                        command=lambda _: self._on_picker_change()).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="📄  PDF", width=90, height=30,
                      fg_color=_RED, hover_color="#B71C1C",
                      command=self._export_pdf).pack(side="left", padx=(12, 4))
        ctk.CTkButton(ctrl, text="📊  CSV", width=90, height=30,
                      command=self._export_csv).pack(side="left", padx=4)

        # Tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew")

        self._tab_main  = self.tabs.add("📊  Barras + Torta")
        self._tab_trend = self.tabs.add("📈  Tendencia")
        self._tab_comp  = self.tabs.add("📉  Comparativo")

        # ── Persistent chart containers ──
        # Use pack inside CTkTabview tab frames — grid weights don't propagate correctly

        # Main tab: detail panel at bottom, chart frame takes remaining space
        self._build_detail_panel()   # packed to bottom first
        self._chart_frame = ctk.CTkFrame(
            self._tab_main, fg_color=("gray86", "gray17"), corner_radius=8
        )
        self._chart_frame.pack(side="top", fill="both", expand=True, pady=(0, 4))

        # Trend tab
        self._trend_frame = ctk.CTkFrame(
            self._tab_trend, fg_color=("gray86", "gray17"), corner_radius=8
        )
        self._trend_frame.pack(fill="both", expand=True)

        # Comparison tab
        self._comp_frame = ctk.CTkFrame(
            self._tab_comp, fg_color=("gray86", "gray17"), corner_radius=8
        )
        self._comp_frame.pack(fill="both", expand=True)

    def _build_detail_panel(self):
        outer = ctk.CTkFrame(
            self._tab_main, fg_color=("gray88", "gray18"), corner_radius=8
        )
        outer.pack(side="bottom", fill="x", pady=(4, 0))

        self._detail_title = ctk.CTkLabel(
            outer,
            text="⬆  Clic en una barra para seleccionar el mes  ·  "
                 "luego clic en un segmento para ver el detalle",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._detail_title.pack(anchor="w", padx=14, pady=(8, 2))

        self._detail_scroll = ctk.CTkScrollableFrame(
            outer, fg_color="transparent", height=110
        )
        self._detail_scroll.pack(fill="x", padx=4, pady=(0, 6))
        self._detail_scroll.grid_columnconfigure(0, weight=1)

    # ─────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────

    def refresh(self, **_):
        self._dark   = ctk.get_appearance_mode().lower() == "dark"
        self._colors = _apply_mpl_theme(self._dark)
        self._moneda = self.db.get_config("moneda", "COP")
        self._tasas  = self.db.get_all_config()

        y, m = int(self.sel_year.get()), int(self.sel_month.get())
        self._sel_period   = f"{y}-{m:02d}"
        self._sel_category = None

        # Defer drawing so Tk finishes sizing all frames before matplotlib draws
        self.after(20, self._draw_all)

    def _draw_all(self):
        self._draw_main_chart()
        self._draw_trend_chart()
        self._draw_comp_chart()

    # ─────────────────────────────────────────
    # Picker change (partial refresh)
    # ─────────────────────────────────────────

    def _on_picker_change(self):
        y, m = int(self.sel_year.get()), int(self.sel_month.get())
        new_period = f"{y}-{m:02d}"
        if new_period == self._sel_period:
            return
        self._sel_period   = new_period
        self._sel_category = None
        if self._fig_main and self._ax_pie:
            self._highlight_bars()
            self._redraw_pie()
            self._update_detail()
        else:
            self.refresh()

    # ─────────────────────────────────────────
    # ── CHART 1: Linked bar + donut ──────────
    # ─────────────────────────────────────────

    def _draw_main_chart(self):
        # Destroy previous canvas widget only (keep _chart_frame alive)
        for w in self._chart_frame.winfo_children():
            w.destroy()
        if self._fig_main:
            plt.close(self._fig_main)
            self._fig_main = None

        c   = self._colors
        bg  = c["bg"]
        txt = c["txt"]

        bar_data          = self.db.get_totales_por_mes(6)
        self._bar_periods = [d["periodo"] for d in bar_data]
        bar_labels        = [periodo_label(p) for p in self._bar_periods]
        bar_totals        = [d["total"]   for d in bar_data]

        if self._sel_period not in self._bar_periods and self._bar_periods:
            self._sel_period = self._bar_periods[-1]

        # Figure with two axes side-by-side
        self._fig_main = plt.figure(figsize=(13, 4.0), facecolor=bg)
        gs = self._fig_main.add_gridspec(
            1, 2, width_ratios=[1.35, 1],
            wspace=0.26, left=0.06, right=0.97, top=0.87, bottom=0.16,
        )
        self._ax_bar = self._fig_main.add_subplot(gs[0])
        self._ax_pie = self._fig_main.add_subplot(gs[1])

        # Draw bars
        self._bars = []
        if bar_totals:
            for i, (lbl, total) in enumerate(zip(bar_labels, bar_totals)):
                sel = self._bar_periods[i] == self._sel_period
                bar = self._ax_bar.bar(
                    lbl, total,
                    color=_BLUE if sel else _BLUE_D,
                    alpha=1.0   if sel else 0.50,
                    linewidth=0, picker=True,
                )[0]
                self._bars.append(bar)

            # bar_label only when we have bars with valid bboxes
            containers = self._ax_bar.containers
            if containers and bar_totals:
                try:
                    self._ax_bar.bar_label(
                        containers[0],
                        labels=[format_currency(v, self._moneda, short=True)
                                for v in bar_totals],
                        padding=3, fontsize=8, color=txt,
                    )
                except Exception:
                    pass  # skip labels if matplotlib can't compute bboxes yet
        else:
            self._ax_bar.text(
                0.5, 0.5, "Sin datos en los últimos 6 meses",
                ha="center", va="center", transform=self._ax_bar.transAxes,
                color=txt, fontsize=11,
            )

        self._ax_bar.set_title(
            "Gastos últimos 6 meses  ·  clic en barra = seleccionar mes",
            fontsize=10, color=txt,
        )
        self._ax_bar.set_ylabel(f"({self._moneda})", fontsize=9)
        self._ax_bar.grid(axis="y", linestyle="--", alpha=0.30)
        self._ax_bar.spines[["top", "right"]].set_visible(False)
        self._ax_bar.tick_params(labelsize=8)

        # Draw initial donut
        self._draw_pie_axes()

        # Embed in container frame — pack fills it completely
        self._canvas_main = FigureCanvasTkAgg(self._fig_main, master=self._chart_frame)
        self._canvas_main.draw()
        self._canvas_main.get_tk_widget().pack(fill="both", expand=True)

        self._fig_main.canvas.mpl_connect("button_press_event", self._on_click)
        self._fig_main.canvas.mpl_connect("motion_notify_event", self._on_hover)

        self._update_detail()

    def _draw_pie_axes(self):
        """(Re)draw the donut chart on self._ax_pie."""
        ax  = self._ax_pie
        ax.clear()
        self._wedges     = []
        self._pie_names  = []
        self._pie_colors = []
        self._pie_totals = []
        self._pie_raw    = []

        bg  = self._colors["bg"]
        txt = self._colors["txt"]

        if not self._sel_period:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", color=txt)
            return

        y, m = map(int, self._sel_period.split("-"))
        MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        lbl_period = f"{MESES[m-1]} {y}"

        data = self.db.get_totales_por_categoria_mes(y, m)
        if not data:
            ax.text(0.5, 0.5, f"Sin datos\n{lbl_period}",
                    ha="center", va="center", color=txt, fontsize=11)
            ax.set_title(f"Distribución — {lbl_period}", fontsize=10, color=txt)
            return

        self._pie_raw    = data
        self._pie_names  = [d["nombre"] for d in data]
        self._pie_colors = [d["color"]  for d in data]
        self._pie_totals = [d["total"]  for d in data]
        total            = sum(self._pie_totals)

        explode = [
            0.08 if n == self._sel_category else 0.0
            for n in self._pie_names
        ]

        wedges, _, autotexts = ax.pie(
            self._pie_totals,
            labels=None,
            colors=self._pie_colors,
            autopct=lambda p: f"{p:.1f}%" if p > 4.5 else "",
            startangle=90,
            pctdistance=0.76,
            explode=explode,
            wedgeprops=dict(width=0.52, edgecolor=bg, linewidth=2, picker=True),
        )
        self._wedges = wedges
        for at in autotexts:
            at.set_fontsize(8)
            at.set_color(txt)

        # Highlight selected wedge
        for w, name in zip(wedges, self._pie_names):
            if name == self._sel_category:
                w.set_linewidth(3)
                w.set_edgecolor(_BLUE)

        # Center label
        ax.text(0, 0, format_currency(total, self._moneda, short=True),
                ha="center", va="center",
                fontsize=10, fontweight="bold", color=txt)

        # Compact legend (top 6)
        patches = [
            mpatches.Patch(
                color=d["color"],
                label=f"{d['nombre'][:13]}: {format_currency(d['total'], self._moneda, short=True)}",
            )
            for d in data[:6]
        ]
        ax.legend(handles=patches, loc="lower center",
                  bbox_to_anchor=(0.5, -0.28), ncol=2,
                  fontsize=7.5, framealpha=0.20)

        hint = (f"  ·  selec: {self._sel_category}" if self._sel_category
                else "  ·  clic en segmento = detalle")
        ax.set_title(f"Distribución — {lbl_period}{hint}", fontsize=9.5, color=txt)

    # ─────────────────────────────────────────
    # Interaction
    # ─────────────────────────────────────────

    def _on_click(self, event):
        if event.inaxes == self._ax_bar:
            for i, bar in enumerate(self._bars):
                if bar.contains(event)[0]:
                    period = self._bar_periods[i]
                    if period == self._sel_period:
                        return
                    self._sel_period   = period
                    self._sel_category = None
                    y, m = map(int, period.split("-"))
                    self.sel_year.set(str(y))
                    self.sel_month.set(f"{m:02d}")
                    self._highlight_bars()
                    self._redraw_pie()
                    self._update_detail()
                    return
        elif event.inaxes == self._ax_pie:
            for i, wedge in enumerate(self._wedges):
                if wedge.contains(event)[0]:
                    name = self._pie_names[i]
                    self._sel_category = None if name == self._sel_category else name
                    self._redraw_pie()
                    self._update_detail()
                    return

    def _on_hover(self, event):
        if not self._fig_main:
            return
        changed = False
        # Bar hover glow
        ax_is_bar = event.inaxes == self._ax_bar
        for i, bar in enumerate(self._bars):
            sel    = self._bar_periods[i] == self._sel_period
            hov    = ax_is_bar and bar.contains(event)[0]
            ta     = 1.0 if (sel or hov) else 0.50
            tc     = _BLUE if (sel or hov) else _BLUE_D
            if abs(bar.get_alpha() - ta) > 0.01:
                bar.set_alpha(ta)
                bar.set_facecolor(tc)
                changed = True
        # Pie hover scale
        if event.inaxes == self._ax_pie and self._wedges:
            for i, w in enumerate(self._wedges):
                hov = w.contains(event)[0]
                sel = i < len(self._pie_names) and self._pie_names[i] == self._sel_category
                tr  = 1.06 if hov else 1.0
                if abs(w.get_radius() - tr) > 0.005 and not sel:
                    w.set_radius(tr)
                    changed = True
        if changed:
            self._fig_main.canvas.draw_idle()

    def _highlight_bars(self):
        for i, bar in enumerate(self._bars):
            sel = self._bar_periods[i] == self._sel_period
            bar.set_alpha(1.0 if sel else 0.50)
            bar.set_facecolor(_BLUE if sel else _BLUE_D)
        if self._fig_main:
            self._fig_main.canvas.draw_idle()

    def _redraw_pie(self):
        self._draw_pie_axes()
        if self._fig_main:
            self._fig_main.canvas.draw_idle()

    # ─────────────────────────────────────────
    # Detail panel
    # ─────────────────────────────────────────

    def _update_detail(self):
        for w in self._detail_scroll.winfo_children():
            w.destroy()

        if not self._sel_period:
            return

        y, m     = map(int, self._sel_period.split("-"))
        last_day = calendar.monthrange(y, m)[1]
        MESES    = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

        all_gastos = self.db.get_gastos(
            fecha_desde=f"{y}-{m:02d}-01",
            fecha_hasta=f"{y}-{m:02d}-{last_day:02d}",
        )

        if self._sel_category:
            gastos    = [g for g in all_gastos
                         if (g.categoria_nombre or "Sin categoría") == self._sel_category]
            total_cat = sum(g.monto for g in gastos)
            cat_color = next(
                (c for n, c in zip(self._pie_names, self._pie_colors)
                 if n == self._sel_category), "#607D8B"
            )
            self._detail_title.configure(
                text=f"● {self._sel_category}  ·  {MESES[m-1]} {y}  ·  "
                     f"{len(gastos)} gastos  ·  {format_currency(total_cat, self._moneda)}"
                     "   — clic nuevamente en el segmento para deseleccionar",
                text_color=cat_color,
            )
            self._render_rows(gastos)
        else:
            total_cop = sum(
                convertir_a_cop(g.monto, g.moneda, self._tasas) if g.moneda != self._moneda
                else g.monto
                for g in all_gastos
            )
            self._detail_title.configure(
                text=f"{MESES[m-1]} {y}  ·  {len(all_gastos)} gastos  ·  "
                     f"Total: {format_currency(total_cop, self._moneda)}"
                     "   — Clic en un segmento de la torta para ver el detalle",
                text_color=("gray20", "gray70"),
            )

            # Multi-currency breakdown
            by_cur: dict = {}
            for g in all_gastos:
                cur = g.moneda or 'COP'
                by_cur[cur] = by_cur.get(cur, 0) + g.monto
            if len(by_cur) > 1:
                fx_row = ctk.CTkFrame(self._detail_scroll, fg_color=("gray85", "gray22"),
                                      corner_radius=6)
                fx_row.pack(fill="x", pady=(2, 4), padx=4)
                ctk.CTkLabel(fx_row, text="💱  Por moneda:",
                             font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(8, 6), pady=5)
                for cur, tot in sorted(by_cur.items()):
                    cop_eq = convertir_a_cop(tot, cur, self._tasas)
                    label_text = format_currency(tot, cur)
                    if cur != 'COP' and cop_eq > 0:
                        label_text += f"  ≈ {format_currency(cop_eq, 'COP')}"
                    ctk.CTkLabel(fx_row, text=label_text,
                                 font=ctk.CTkFont(size=11),
                                 text_color=_BLUE).pack(side="left", padx=(0, 12), pady=5)

            if self._pie_raw and total_cop > 0:
                for d in self._pie_raw:
                    row_f = ctk.CTkFrame(self._detail_scroll,
                                         fg_color="transparent", corner_radius=4)
                    row_f.pack(fill="x", pady=1, padx=4)
                    ctk.CTkLabel(row_f, text="●", text_color=d["color"],
                                 font=ctk.CTkFont(size=13), width=22).pack(
                        side="left", padx=(6, 2))
                    ctk.CTkLabel(row_f, text=d["nombre"],
                                 font=ctk.CTkFont(size=12),
                                 anchor="w").pack(side="left", fill="x", expand=True)
                    pct = d["total"] / total_cop * 100 if total_cop > 0 else 0
                    ctk.CTkLabel(
                        row_f,
                        text=f"{format_currency(d['total'], self._moneda)}  ({pct:.1f}%)",
                        font=ctk.CTkFont(size=12), text_color=_RED,
                    ).pack(side="right", padx=10)

    def _render_rows(self, gastos):
        for i, g in enumerate(gastos):
            bg    = ("gray90", "gray20") if i % 2 == 0 else ("gray86", "gray17")
            row_f = ctk.CTkFrame(self._detail_scroll, fg_color=bg, corner_radius=4)
            row_f.pack(fill="x", pady=1, padx=2)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=format_date(g.fecha),
                         width=84, font=ctk.CTkFont(size=11),
                         text_color="gray").grid(row=0, column=0, padx=(8, 4), pady=5)
            ctk.CTkLabel(row_f, text=g.descripcion, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(
                row=0, column=1, sticky="ew", padx=4, pady=5)

            # Method + cuotas badge
            method_txt = g.metodo_pago
            cuotas = getattr(g, 'cuotas', 1) or 1
            if cuotas > 1:
                method_txt += f"  ·  {cuotas} cuotas"
            ctk.CTkLabel(row_f, text=method_txt, font=ctk.CTkFont(size=11),
                         text_color="gray", width=190).grid(row=0, column=2, padx=4, pady=5)

            if g.notas:
                ctk.CTkLabel(row_f, text=f"📝 {g.notas}", font=ctk.CTkFont(size=10),
                             text_color="gray", anchor="w").grid(
                    row=0, column=3, padx=4, pady=5)

            # Amount — show original currency + COP equivalent if foreign
            moneda_g = getattr(g, 'moneda', 'COP') or 'COP'
            amt_txt  = format_currency(g.monto, moneda_g)
            if moneda_g != 'COP':
                cop_eq = convertir_a_cop(g.monto, moneda_g, self._tasas)
                if cop_eq > 0:
                    amt_txt += f"\n≈ {format_currency(cop_eq, 'COP')}"
            ctk.CTkLabel(
                row_f, text=amt_txt,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_RED, width=140, justify="right",
            ).grid(row=0, column=4, padx=(4, 10), pady=5)

    # ─────────────────────────────────────────
    # ── CHART 2: Trend line ──────────────────
    # ─────────────────────────────────────────

    def _draw_trend_chart(self):
        for w in self._trend_frame.winfo_children():
            w.destroy()
        if self._trend_fig:
            plt.close(self._trend_fig)
            self._trend_fig = None

        c   = self._colors
        bg  = c["bg"]
        txt = c["txt"]

        data   = self.db.get_totales_por_mes(12)
        labels = [periodo_label(d["periodo"]) for d in data]
        totals = [d["total"] for d in data]

        self._trend_fig, ax = plt.subplots(figsize=(10, 4.6))
        self._trend_fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        line, = ax.plot(
            labels, totals, marker="o", color=_GREEN, linewidth=2.5,
            markersize=7, markerfacecolor=_GREEN,
            markeredgecolor=bg, markeredgewidth=2, picker=6,
        )
        ax.fill_between(range(len(labels)), totals, alpha=0.10, color=_GREEN)

        for i, v in enumerate(totals):
            ax.annotate(
                format_currency(v, self._moneda, short=True),
                (i, v), textcoords="offset points", xytext=(0, 11),
                ha="center", fontsize=8, color=txt, alpha=0.85,
            )

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=9)
        ax.set_title("Tendencia de gasto mensual — últimos 12 meses", fontsize=12, color=txt)
        ax.set_ylabel(f"({self._moneda})", fontsize=9)
        ax.grid(linestyle="--", alpha=0.30)
        ax.spines[["top", "right"]].set_visible(False)
        self._trend_fig.tight_layout()

        self._trend_canvas = FigureCanvasTkAgg(self._trend_fig, master=self._trend_frame)
        self._trend_canvas.draw()
        self._trend_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Hover tooltip
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=c["panel"], ec=_GREEN, lw=1.5),
            fontsize=9, color=txt, visible=False,
        )

        def _hover(event):
            if event.inaxes != ax:
                if annot.get_visible():
                    annot.set_visible(False)
                    self._trend_canvas.draw_idle()
                return
            cont, ind = line.contains(event)
            if cont:
                idx = ind["ind"][0]
                annot.xy = (idx, totals[idx])
                annot.set_text(f"{labels[idx]}\n{format_currency(totals[idx], self._moneda)}")
                annot.set_visible(True)
                self._trend_canvas.draw_idle()
            elif annot.get_visible():
                annot.set_visible(False)
                self._trend_canvas.draw_idle()

        self._trend_fig.canvas.mpl_connect("motion_notify_event", _hover)

    # ─────────────────────────────────────────
    # ── CHART 3: Comparison bars ─────────────
    # ─────────────────────────────────────────

    def _draw_comp_chart(self):
        for w in self._comp_frame.winfo_children():
            w.destroy()
        if self._comp_fig:
            plt.close(self._comp_fig)
            self._comp_fig = None

        c   = self._colors
        bg  = c["bg"]
        txt = c["txt"]

        periodos   = ultimos_n_meses(3)
        cats_data: Dict[str, dict] = {}
        for p in periodos:
            yp, mp = map(int, p.split("-"))
            for d in self.db.get_totales_por_categoria_mes(yp, mp):
                cats_data.setdefault(d["nombre"], {"color": d["color"], "values": {}})
                cats_data[d["nombre"]]["values"][p] = d["total"]

        sorted_cats = sorted(
            cats_data.items(),
            key=lambda x: sum(x[1]["values"].values()),
            reverse=True,
        )[:7]

        if not sorted_cats:
            ctk.CTkLabel(self._comp_frame, text="Sin datos suficientes.",
                         text_color="gray").pack(pady=40)
            return

        labels = [periodo_label(p) for p in periodos]
        x      = np.arange(len(labels))
        n      = len(sorted_cats)
        width  = 0.78 / n

        self._comp_fig, ax = plt.subplots(figsize=(10, 4.8))
        self._comp_fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        bar_groups = []
        for i, (cat, info) in enumerate(sorted_cats):
            vals   = [info["values"].get(p, 0) for p in periodos]
            offset = (i - n / 2 + 0.5) * width
            bars   = ax.bar(x + offset, vals, width, label=cat,
                            color=info["color"], alpha=0.85, picker=True)
            bar_groups.append((cat, bars, vals))

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_title(
            "Comparativo por categoría — últimos 3 meses  ·  hover para ver valor",
            fontsize=11, color=txt,
        )
        ax.set_ylabel(f"({self._moneda})", fontsize=9)
        ax.legend(fontsize=8.5, loc="upper right")
        ax.grid(axis="y", linestyle="--", alpha=0.30)
        ax.spines[["top", "right"]].set_visible(False)
        self._comp_fig.tight_layout()

        self._comp_canvas = FigureCanvasTkAgg(self._comp_fig, master=self._comp_frame)
        self._comp_canvas.draw()
        self._comp_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Hover tooltip
        annot = ax.annotate(
            "", xy=(0, 0), xytext=(8, 8), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=c["panel"], ec=_BLUE, lw=1.5),
            fontsize=9, color=txt, visible=False,
        )

        def _hover(event):
            if event.inaxes != ax:
                if annot.get_visible():
                    annot.set_visible(False)
                    self._comp_canvas.draw_idle()
                return
            for cat_name, bars, vals in bar_groups:
                for j, bar in enumerate(bars):
                    if bar.contains(event)[0]:
                        annot.xy = (bar.get_x() + bar.get_width() / 2, bar.get_height())
                        annot.set_text(
                            f"{cat_name}\n{labels[j]}\n"
                            f"{format_currency(vals[j], self._moneda)}"
                        )
                        annot.set_visible(True)
                        self._comp_canvas.draw_idle()
                        return
            if annot.get_visible():
                annot.set_visible(False)
                self._comp_canvas.draw_idle()

        self._comp_fig.canvas.mpl_connect("motion_notify_event", _hover)

    # ─────────────────────────────────────────
    # Helper: matplotlib fig → PNG bytes
    # ─────────────────────────────────────────

    @staticmethod
    def _fig_to_buf(fig, dpi: int = 150) -> io.BytesIO:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        buf.seek(0)
        return buf

    # ─────────────────────────────────────────
    # ── PDF Export (reportlab) ───────────────
    # ─────────────────────────────────────────

    def _export_pdf(self):
        from tkinter import filedialog, messagebox

        if not HAS_MPL:
            messagebox.showerror("Error", "matplotlib no está instalado.")
            return

        year  = int(self.sel_year.get())
        month = int(self.sel_month.get())
        MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        MESES_A = ["Ene","Feb","Mar","Abr","May","Jun",
                   "Jul","Ago","Sep","Oct","Nov","Dic"]

        default = f"reporte_{MESES_A[month-1]}_{year}.pdf"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=default,
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
        )
        if not path:
            return

        moneda   = self.db.get_config("moneda", "COP")
        nombre   = self.db.get_config("nombre_usuario", "Usuario")
        presup   = float(self.db.get_config("presupuesto_mensual", "0") or "0")
        last_day = calendar.monthrange(year, month)[1]
        gastos   = self.db.get_gastos(
            fecha_desde=f"{year}-{month:02d}-01",
            fecha_hasta=f"{year}-{month:02d}-{last_day:02d}",
        )
        total_mes = sum(g.monto for g in gastos)
        cat_data  = self.db.get_totales_por_categoria_mes(year, month)
        bar_data  = self.db.get_totales_por_mes(6)

        # ── Generate chart images ──────────────────────────
        plt.rcParams.update({
            "figure.facecolor": "white", "axes.facecolor": "white",
            "axes.edgecolor": "#cccccc", "axes.labelcolor": "#111111",
            "text.color": "#111111", "xtick.color": "#111111",
            "ytick.color": "#111111", "grid.color": "#dddddd",
            "legend.facecolor": "#f0f4ff", "legend.edgecolor": "#cccccc",
            "legend.labelcolor": "#111111",
        })

        # Chart A: bar + donut side by side
        fig_a = plt.figure(figsize=(10, 3.8), facecolor="white")
        gs_a  = fig_a.add_gridspec(1, 2, width_ratios=[1.3, 1],
                                    wspace=0.25, left=0.07, right=0.97,
                                    top=0.88, bottom=0.16)
        ax_b = fig_a.add_subplot(gs_a[0])
        ax_p = fig_a.add_subplot(gs_a[1])

        # Bars
        b_labels = [periodo_label(d["periodo"]) for d in bar_data]
        b_totals = [d["total"] for d in bar_data]
        b_colors = [_BLUE if d["periodo"] == f"{year}-{month:02d}" else "#90CAF9"
                    for d in bar_data]
        bp = ax_b.bar(b_labels, b_totals, color=b_colors, alpha=0.92, linewidth=0)
        if b_totals:
            try:
                ax_b.bar_label(bp,
                               labels=[format_currency(v, moneda, short=True) for v in b_totals],
                               padding=3, fontsize=7.5)
            except Exception:
                pass
        ax_b.set_title(f"Gastos últimos 6 meses", fontsize=10)
        ax_b.set_ylabel(f"({moneda})", fontsize=8)
        ax_b.grid(axis="y", linestyle="--", alpha=0.4)
        ax_b.spines[["top", "right"]].set_visible(False)
        ax_b.tick_params(axis="x", labelsize=8, rotation=20)

        # Donut
        if cat_data:
            vals = [d["total"] for d in cat_data]
            clrs = [d["color"] for d in cat_data]
            nms  = [d["nombre"] for d in cat_data]
            w2, _, at2 = ax_p.pie(
                vals, colors=clrs,
                autopct=lambda p: f"{p:.1f}%" if p > 5 else "",
                startangle=90, pctdistance=0.76,
                wedgeprops=dict(width=0.52, edgecolor="white", linewidth=1.5),
            )
            for at in at2:
                at.set_fontsize(7.5)
            ax_p.legend(w2,
                        [f"{n[:12]}: {format_currency(v, moneda, short=True)}"
                         for n, v in zip(nms, vals)],
                        loc="lower center", bbox_to_anchor=(0.5, -0.32),
                        ncol=2, fontsize=6.5, framealpha=0.5)
            ax_p.text(0, 0, format_currency(total_mes, moneda, short=True),
                      ha="center", va="center", fontsize=9, fontweight="bold")
        ax_p.set_title(f"Distribución — {MESES[month-1]} {year}", fontsize=10)

        buf_a = self._fig_to_buf(fig_a, dpi=160)
        plt.close(fig_a)

        # Chart B: trend line
        t_data   = self.db.get_totales_por_mes(12)
        t_labels = [periodo_label(d["periodo"]) for d in t_data]
        t_totals = [d["total"] for d in t_data]

        fig_b, ax_t = plt.subplots(figsize=(10, 3.2), facecolor="white")
        ax_t.set_facecolor("white")
        ax_t.plot(t_labels, t_totals, marker="o", color=_GREEN, linewidth=2.5,
                  markersize=6, markerfacecolor=_GREEN,
                  markeredgecolor="white", markeredgewidth=2)
        ax_t.fill_between(range(len(t_labels)), t_totals, alpha=0.10, color=_GREEN)
        for i, v in enumerate(t_totals):
            ax_t.annotate(format_currency(v, moneda, short=True),
                          (i, v), textcoords="offset points", xytext=(0, 8),
                          ha="center", fontsize=7, alpha=0.85)
        ax_t.set_xticks(range(len(t_labels)))
        ax_t.set_xticklabels(t_labels, rotation=28, ha="right", fontsize=8)
        ax_t.set_title("Tendencia — últimos 12 meses", fontsize=10)
        ax_t.set_ylabel(f"({moneda})", fontsize=8)
        ax_t.grid(linestyle="--", alpha=0.35)
        ax_t.spines[["top", "right"]].set_visible(False)
        fig_b.tight_layout()

        buf_b = self._fig_to_buf(fig_b, dpi=160)
        plt.close(fig_b)

        # ── Restore app theme ──────────────────────────────
        _apply_mpl_theme(self._dark)

        # ── Build PDF ─────────────────────────────────────
        if HAS_RL:
            self._build_pdf_reportlab(
                path, year, month, moneda, nombre, presup,
                gastos, total_mes, cat_data, buf_a, buf_b,
                MESES, MESES_A,
            )
        else:
            self._build_pdf_matplotlib(
                path, year, month, moneda, nombre, presup,
                gastos, total_mes, cat_data, buf_a, buf_b,
                MESES,
            )

        from tkinter import messagebox
        messagebox.showinfo("PDF generado", f"Reporte guardado en:\n{path}")

    # ── ReportLab PDF ────────────────────────────────────────────────────────

    def _build_pdf_reportlab(self, path, year, month, moneda, nombre, presup,
                              gastos, total_mes, cat_data, buf_a, buf_b,
                              MESES, MESES_A):
        PAGE_W, PAGE_H = A4         # 595 x 842 pt
        MARGIN = 1.5 * cm
        CW     = PAGE_W - 2 * MARGIN   # content width ≈ 512 pt

        # ── Colour objects ─────────────────────────────────
        C_BLUE    = rl_colors.HexColor(_BLUE)
        C_BLUE_D  = rl_colors.HexColor(_BLUE_D)
        C_GREEN   = rl_colors.HexColor(_GREEN)
        C_RED     = rl_colors.HexColor(_RED)
        C_ORANGE  = rl_colors.HexColor(_ORANGE)
        C_GREY    = rl_colors.HexColor("#555555")
        C_LGREY   = rl_colors.HexColor("#f0f4ff")
        C_ROW1    = rl_colors.HexColor("#f7f9ff")
        C_ROW2    = rl_colors.white
        C_HDR     = rl_colors.HexColor("#1565C0")

        # ── Colour helpers ──────────────────────────────────
        C_RED2    = rl_colors.HexColor("#C62828")
        C_BLUE2   = rl_colors.HexColor("#0D47A1")

        # ── Styles ─────────────────────────────────────────
        SS  = getSampleStyleSheet()
        def style(name, **kw):
            base = SS["Normal"].clone(name)
            for k, v in kw.items():
                setattr(base, k, v)
            return base

        s_title   = style("Title2",  fontSize=26, textColor=rl_colors.white,
                           fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=0)
        s_sub     = style("Sub",     fontSize=12, textColor=rl_colors.HexColor("#BBDEFB"),
                           fontName="Helvetica", alignment=TA_CENTER)
        s_h2      = style("H2",      fontSize=12, textColor=C_BLUE_D,
                           fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3)
        s_body    = style("Body2",   fontSize=9,  textColor=rl_colors.HexColor("#333333"),
                           fontName="Helvetica")
        s_small   = style("Small",   fontSize=7.5, textColor=C_GREY, fontName="Helvetica")
        s_mlbl    = style("MLbl",    fontSize=7.5, textColor=rl_colors.white,
                           fontName="Helvetica-Bold", alignment=TA_CENTER)
        s_mval    = style("MVal",    fontSize=19, textColor=rl_colors.HexColor("#111111"),
                           fontName="Helvetica-Bold", alignment=TA_CENTER)
        s_mnote   = style("MNote",   fontSize=7.5, textColor=C_GREY,
                           fontName="Helvetica", alignment=TA_CENTER)
        s_tbl_hdr = style("TH",      fontSize=8.5, textColor=rl_colors.white,
                           fontName="Helvetica-Bold", alignment=TA_CENTER)
        s_tbl_r   = style("TR",      fontSize=8.5, textColor=rl_colors.HexColor("#111111"),
                           fontName="Helvetica")
        s_tbl_rb  = style("TRB",     fontSize=8.5, textColor=rl_colors.HexColor("#111111"),
                           fontName="Helvetica-Bold")
        s_info_lbl = style("ILbl",   fontSize=7.5, textColor=rl_colors.white,
                            fontName="Helvetica-Bold", alignment=TA_CENTER)
        s_info_val = style("IVal",   fontSize=9.5, textColor=rl_colors.white,
                            fontName="Helvetica-Bold", alignment=TA_CENTER)

        # ── On-page header/footer ───────────────────────────
        def _on_page(canvas_pdf, doc):
            canvas_pdf.saveState()
            # Top accent bar
            canvas_pdf.setFillColor(C_BLUE)
            canvas_pdf.rect(0, PAGE_H - 0.55 * cm, PAGE_W, 0.55 * cm, fill=1, stroke=0)
            canvas_pdf.setFillColor(rl_colors.white)
            canvas_pdf.setFont("Helvetica-Bold", 8)
            canvas_pdf.drawString(MARGIN, PAGE_H - 0.38 * cm,
                                  f"REPORTE DE GASTOS — {MESES[month-1].upper()} {year}")
            canvas_pdf.setFont("Helvetica", 8)
            canvas_pdf.drawRightString(
                PAGE_W - MARGIN, PAGE_H - 0.38 * cm,
                f"GastosApp  ·  {nombre}"
            )
            # Bottom footer line
            canvas_pdf.setStrokeColor(rl_colors.HexColor("#dddddd"))
            canvas_pdf.line(MARGIN, 1.0 * cm, PAGE_W - MARGIN, 1.0 * cm)
            canvas_pdf.setFillColor(C_GREY)
            canvas_pdf.setFont("Helvetica", 7.5)
            canvas_pdf.drawCentredString(
                PAGE_W / 2, 0.6 * cm,
                f"Página {doc.page}  ·  Generado el {date.today().strftime('%d/%m/%Y')}"
            )
            canvas_pdf.restoreState()

        # ── Document ────────────────────────────────────────
        doc = SimpleDocTemplate(
            path, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=1.6 * cm, bottomMargin=1.4 * cm,
        )

        story = []

        # ════════════════════════════════════════
        # PAGE 1 — Cover
        # ════════════════════════════════════════

        # ── Hero banner (2-row: main title + dark accent strip) ────
        hero_data = [
            [Paragraph("📊  REPORTE DE GASTOS", s_title)],
            [Paragraph(f"{MESES[month-1].upper()}  {year}", s_sub)],
        ]
        hero_tbl = Table(hero_data, colWidths=[CW])
        hero_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), C_BLUE),
            ("BACKGROUND",    (0, 1), (0, 1), C_BLUE_D),
            ("TOPPADDING",    (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        story.append(hero_tbl)
        story.append(Spacer(1, 0.3 * cm))

        # ── Info bar (dark, 3 cols: usuario / generado / moneda) ───
        info_data = [[
            Paragraph(f"👤  {nombre}",                     s_info_val),
            Paragraph(f"📅  {date.today().strftime('%d/%m/%Y')}", s_info_val),
            Paragraph(f"💱  {moneda}",                     s_info_val),
        ]]
        info_tbl = Table(info_data, colWidths=[CW/3]*3)
        info_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), rl_colors.HexColor("#263238")),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("LINEBEFORE",    (1, 0), (2, -1), 0.5, rl_colors.HexColor("#546E7A")),
        ]))
        story.append(info_tbl)
        story.append(Spacer(1, 0.45 * cm))

        # ── Metric cards ────────────────────────────────────
        # Design: solid colored header row + white value row + light note row
        pct       = total_mes / presup * 100 if presup > 0 else 0
        pct_color = C_GREEN if pct < 75 else C_ORANGE if pct < 100 else C_RED
        avg_gasto = total_mes / len(gastos) if gastos else 0

        GAP = 0.2 * cm
        CW3 = (CW - 2 * GAP) / 3

        def _mcard(label, icon, value_txt, note_txt, hdr_color, val_color):
            s_v = style(f"MV{label}", fontSize=18, textColor=val_color,
                        fontName="Helvetica-Bold", alignment=TA_CENTER)
            t = Table(
                [[Paragraph(f"{icon}  {label}", s_mlbl)],
                 [Paragraph(value_txt, s_v)],
                 [Paragraph(note_txt,  s_mnote)]],
                colWidths=[CW3],
                rowHeights=[0.62 * cm, 0.95 * cm, 0.52 * cm],
            )
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), hdr_color),
                ("BACKGROUND",    (0, 1), (-1, 1), rl_colors.white),
                ("BACKGROUND",    (0, 2), (-1, 2), C_LGREY),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                ("BOX",           (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#cccccc")),
            ]))
            return t

        if presup > 0:
            card3 = _mcard("PRESUPUESTO USADO", "📊",
                           f"{pct:.1f}%",
                           f"de {format_currency(presup, moneda, short=True)}",
                           pct_color, pct_color)
        else:
            card3 = _mcard("CATEGORÍAS", "🏷",
                           str(len(cat_data)), "con gasto este mes",
                           C_GREEN, C_GREEN)

        card1 = _mcard("TOTAL GASTADO",   "💰",
                       format_currency(total_mes, moneda, short=True), " ",
                       C_RED, C_RED2)
        card2 = _mcard("TRANSACCIONES",   "🧾",
                       str(len(gastos)),
                       f"promedio {format_currency(avg_gasto, moneda, short=True)}",
                       C_BLUE, C_BLUE2)

        cards_row = Table([[card1, Spacer(GAP, 1), card2, Spacer(GAP, 1), card3]],
                           colWidths=[CW3, GAP, CW3, GAP, CW3])
        cards_row.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        story.append(cards_row)
        story.append(Spacer(1, 0.5 * cm))

        # Category distribution table
        story.append(Paragraph("Distribución por categoría", s_h2))
        story.append(HRFlowable(width=CW, thickness=1, color=C_BLUE, spaceAfter=6))

        if cat_data:
            BAR_W = CW * 0.20   # width of mini-bar column

            def _mini_bar(pct_val: float, hex_color: str) -> Table:
                filled = max(pct_val / 100, 0.02)
                w_f    = BAR_W * filled
                w_e    = BAR_W - w_f
                cells  = [["", ""]] if w_e > 0 else [[""]]
                cws    = [w_f, w_e] if w_e > 0 else [w_f]
                bt = Table(cells, colWidths=cws, rowHeights=[0.28 * cm])
                bt.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (0, 0), rl_colors.HexColor(hex_color)),
                    ("BACKGROUND",    (1, 0), (1, 0), rl_colors.HexColor("#e8eaf6"))
                    if w_e > 0 else ("BACKGROUND", (0, 0), (0, 0),
                                     rl_colors.HexColor(hex_color)),
                    ("TOPPADDING",    (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                ]))
                return bt

            s_th = style("TH2", fontSize=8.5, textColor=rl_colors.white,
                         fontName="Helvetica-Bold", alignment=TA_CENTER)
            cat_hdr = [
                Paragraph("Categoría",   s_th),
                Paragraph("Monto",       style("th2r", fontSize=8.5,
                                               textColor=rl_colors.white,
                                               fontName="Helvetica-Bold",
                                               alignment=TA_RIGHT)),
                Paragraph("%",           s_th),
                Paragraph("Distribución", s_th),
            ]
            cat_rows = [cat_hdr]
            for i, d in enumerate(cat_data[:14]):
                pct_cat = d["total"] / total_mes * 100 if total_mes > 0 else 0
                cat_rows.append([
                    Paragraph(f'<font color="{d["color"]}">■</font>  {d["nombre"]}',
                               s_tbl_r),
                    Paragraph(format_currency(d["total"], moneda),
                               style(f"ta{i}", fontSize=8.5, fontName="Helvetica",
                                     alignment=TA_RIGHT,
                                     textColor=rl_colors.HexColor("#111111"))),
                    Paragraph(f"{pct_cat:.1f}%",
                               style(f"tp{i}", fontSize=8.5, fontName="Helvetica",
                                     alignment=TA_CENTER,
                                     textColor=rl_colors.HexColor("#444444"))),
                    _mini_bar(pct_cat, d["color"]),
                ])

            cat_tbl = Table(cat_rows,
                            colWidths=[CW*0.40, CW*0.20, CW*0.08, BAR_W + CW*0.06])
            cat_style = [
                ("BACKGROUND",    (0, 0), (-1, 0), C_HDR),
                ("TOPPADDING",    (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING",    (0, 1), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#dddddd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_ROW1, C_ROW2]),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]
            cat_tbl.setStyle(TableStyle(cat_style))
            story.append(cat_tbl)

        story.append(PageBreak())

        # ════════════════════════════════════════
        # PAGE 2 — Charts (bar + donut + trend)
        # ════════════════════════════════════════
        story.append(Paragraph("Análisis gráfico", s_h2))
        story.append(HRFlowable(width=CW, thickness=1, color=C_BLUE, spaceAfter=8))

        # Bar + donut
        story.append(Paragraph(
            f"Gastos últimos 6 meses  ·  Distribución por categoría — {MESES[month-1]} {year}",
            s_small,
        ))
        story.append(Spacer(1, 0.2 * cm))
        img_a = RLImage(buf_a, width=CW, height=CW * 0.38)
        story.append(img_a)
        story.append(Spacer(1, 0.5 * cm))

        # Trend
        story.append(Paragraph("Tendencia de gasto mensual — últimos 12 meses", s_small))
        story.append(Spacer(1, 0.2 * cm))
        img_b = RLImage(buf_b, width=CW, height=CW * 0.32)
        story.append(img_b)

        story.append(PageBreak())

        # ════════════════════════════════════════
        # PAGE 3+ — Expense table
        # ════════════════════════════════════════
        story.append(Paragraph(
            f"Detalle de gastos — {MESES[month-1]} {year}", s_h2
        ))
        story.append(HRFlowable(width=CW, thickness=1, color=C_BLUE, spaceAfter=6))

        col_w = [CW*0.10, CW*0.31, CW*0.17, CW*0.17, CW*0.16, CW*0.09]
        s_thr = style("THR2", fontSize=8.5, textColor=rl_colors.white,
                      fontName="Helvetica-Bold", alignment=TA_RIGHT)
        t_hdr = [[
            Paragraph("Fecha",       s_tbl_hdr),
            Paragraph("Descripción", s_tbl_hdr),
            Paragraph("Categoría",   s_tbl_hdr),
            Paragraph("Método",      s_tbl_hdr),
            Paragraph("Monto",       s_thr),
            Paragraph("Cuotas",      s_tbl_hdr),
        ]]

        t_rows = list(t_hdr)
        for i, g in enumerate(gastos):
            cat_dot = (f'<font color="{g.categoria_color or "#607D8B"}">■</font> '
                       if g.categoria_color else "")
            cuotas_g = getattr(g, 'cuotas', 1) or 1
            moneda_g  = getattr(g, 'moneda', 'COP') or 'COP'
            cuotas_txt = "contado" if cuotas_g <= 1 else f"{cuotas_g}x"
            monto_txt  = format_currency(g.monto, moneda_g)
            t_rows.append([
                Paragraph(format_date(g.fecha), s_tbl_r),
                Paragraph((g.descripcion[:38] + "…") if len(g.descripcion) > 38
                          else g.descripcion, s_tbl_r),
                Paragraph(f"{cat_dot}{g.categoria_nombre or '—'}", s_tbl_r),
                Paragraph(g.metodo_pago.replace("Débito/Transferencia", "Débito"), s_tbl_r),
                Paragraph(monto_txt,
                          style(f"TA{i}", fontSize=8.5, fontName="Helvetica",
                                alignment=TA_RIGHT,
                                textColor=rl_colors.HexColor("#C62828"))),
                Paragraph(cuotas_txt,
                          style(f"CQ{i}", fontSize=8, fontName="Helvetica",
                                alignment=TA_CENTER,
                                textColor=C_BLUE if cuotas_g > 1 else C_GREY)),
            ])

        # Total row
        t_rows.append([
            Paragraph("", s_tbl_rb),
            Paragraph(f"TOTAL  —  {len(gastos)} transacciones", s_tbl_rb),
            Paragraph("", s_tbl_rb),
            Paragraph("", s_tbl_rb),
            Paragraph(format_currency(total_mes, moneda),
                      style("TAB", fontSize=9, fontName="Helvetica-Bold",
                            alignment=TA_RIGHT,
                            textColor=rl_colors.HexColor("#B71C1C"))),
            Paragraph("", s_tbl_rb),
        ])

        expense_tbl = Table(t_rows, colWidths=col_w, repeatRows=1)
        expense_tbl.setStyle(TableStyle([
            # Header
            ("BACKGROUND",    (0, 0), (-1, 0), C_HDR),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            # Grid
            ("LINEBELOW",     (0, 0), (-1, -2), 0.3, rl_colors.HexColor("#dddddd")),
            # Alternating rows
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [C_ROW1, C_ROW2]),
            # Total row
            ("BACKGROUND",    (0, -1), (-1, -1), rl_colors.HexColor("#E3F2FD")),
            ("LINEABOVE",     (0, -1), (-1, -1), 1.0, C_BLUE),
        ]))
        story.append(expense_tbl)

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    # ── Matplotlib fallback PDF ─────────────────────────────────────────────

    def _build_pdf_matplotlib(self, path, year, month, moneda, nombre, presup,
                               gastos, total_mes, cat_data, buf_a, buf_b, MESES):
        from PIL import Image as PILImage
        import numpy as np

        with PdfPages(path) as pdf:
            # Page 1: cover
            fig, ax = plt.subplots(figsize=(8.3, 11.7))
            fig.patch.set_facecolor("white")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

            ax.add_patch(mpatches.FancyBboxPatch(
                (0, 0.90), 1, 0.10, boxstyle="square",
                facecolor=_BLUE, edgecolor="none"
            ))
            ax.text(0.5, 0.955, "REPORTE DE GASTOS", ha="center", va="center",
                    fontsize=22, fontweight="bold", color="white")
            ax.text(0.5, 0.910, f"{MESES[month-1].upper()}  {year}",
                    ha="center", va="center", fontsize=13, color="#BBDEFB")
            ax.text(0.05, 0.875, f"Usuario: {nombre}  ·  {date.today().strftime('%d/%m/%Y')}",
                    fontsize=10, color="#333333")

            pct = total_mes / presup * 100 if presup > 0 else 0
            def _mcell(x, label, val, clr):
                ax.add_patch(mpatches.FancyBboxPatch(
                    (x, 0.79), 0.28, 0.07, boxstyle="round,pad=0.01",
                    facecolor=clr, edgecolor="none", alpha=0.12
                ))
                ax.text(x+0.14, 0.845, label, ha="center", fontsize=8, color="#555")
                ax.text(x+0.14, 0.808, val, ha="center", fontsize=13,
                        fontweight="bold", color=clr)

            _mcell(0.03, "Total gastado",
                   format_currency(total_mes, moneda, short=True), _RED)
            _mcell(0.36, "Transacciones", str(len(gastos)), _BLUE)
            pct_c = _GREEN if pct < 75 else _ORANGE if pct < 100 else _RED
            _mcell(0.69, "Presupuesto", f"{pct:.1f}%" if presup>0 else "—", pct_c)

            ax.text(0.05, 0.765, "Distribución por categoría",
                    fontsize=12, fontweight="bold", color="#111")
            ax.plot([0.05, 0.95], [0.750, 0.750], color="#cccccc", lw=0.8)

            y_pos = 0.730
            for d in cat_data[:16]:
                pct_cat = d["total"] / total_mes * 100 if total_mes > 0 else 0
                ax.add_patch(mpatches.Circle((0.038, y_pos+0.005), 0.005,
                                             facecolor=d["color"], edgecolor="none"))
                ax.text(0.05, y_pos, d["nombre"][:22], fontsize=8.5, color="#111")
                ax.text(0.56, y_pos, format_currency(d["total"], moneda),
                        fontsize=8.5, color="#111")
                ax.text(0.76, y_pos, f"{pct_cat:.1f}%", fontsize=8.5, color="#555")
                bw = min(pct_cat/100*0.09, 0.09)
                ax.add_patch(mpatches.Rectangle(
                    (0.86, y_pos+0.001), bw, 0.009,
                    facecolor=d["color"], edgecolor="none", alpha=0.75
                ))
                y_pos -= 0.021
                if y_pos < 0.06:
                    break

            ax.text(0.5, 0.025, "GastosApp — generado automáticamente",
                    ha="center", fontsize=8, color="#aaa")
            pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

            # Page 2: charts
            fig2, axes = plt.subplots(2, 1, figsize=(11, 8),
                                       facecolor="white")
            for sub_ax in axes:
                sub_ax.axis("off")
            img_a = PILImage.open(buf_a)
            img_b = PILImage.open(buf_b)
            axes[0].imshow(np.array(img_a))
            axes[1].imshow(np.array(img_b))
            axes[0].set_title(f"Gastos por mes + Distribución — {MESES[month-1]} {year}",
                               fontsize=11, fontweight="bold", pad=8)
            axes[1].set_title("Tendencia anual", fontsize=11,
                               fontweight="bold", pad=8)
            fig2.tight_layout()
            pdf.savefig(fig2, bbox_inches="tight"); plt.close(fig2)

            # Page 3+: table
            PAGE_ROWS = 28
            pages = max(1, (len(gastos) + PAGE_ROWS - 1) // PAGE_ROWS)
            for pg in range(pages):
                chunk = gastos[pg*PAGE_ROWS:(pg+1)*PAGE_ROWS]
                fig3, ax3 = plt.subplots(figsize=(11, 8.5), facecolor="white")
                ax3.axis("off")
                sfx = f" ({pg+1}/{pages})" if pages > 1 else ""
                ax3.set_title(f"Detalle — {MESES[month-1]} {year}{sfx}",
                              fontsize=13, fontweight="bold", pad=12)
                data_rows = [
                    [format_date(g.fecha),
                     (g.descripcion[:38]+"…") if len(g.descripcion)>38 else g.descripcion,
                     g.categoria_nombre or "—",
                     g.metodo_pago,
                     format_currency(g.monto, moneda)]
                    for g in chunk
                ]
                data_rows.append(["", f"TOTAL ({len(gastos)} gastos)", "", "",
                                   format_currency(total_mes, moneda)])
                tbl = ax3.table(
                    cellText=data_rows,
                    colLabels=["Fecha","Descripción","Categoría","Método","Monto"],
                    colWidths=[0.10, 0.34, 0.18, 0.22, 0.13],
                    cellLoc="left", loc="center",
                )
                tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1, 1.4)
                for j in range(5):
                    tbl[0,j].set_facecolor(_BLUE)
                    tbl[0,j].set_text_props(color="white", fontweight="bold")
                for j in range(5):
                    tbl[len(data_rows), j].set_text_props(fontweight="bold")
                pdf.savefig(fig3, bbox_inches="tight"); plt.close(fig3)

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
        MESES_A = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"gastos_{MESES_A[month-1]}_{year}.csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Fecha","Descripción","Categoría","Método de pago",
                             "Tarjeta","Monto","Corte","Notas"])
            for g in gastos:
                writer.writerow([g.fecha, g.descripcion, g.categoria_nombre or "",
                                 g.metodo_pago, g.tarjeta_nombre or "",
                                 g.monto, g.corte_periodo or "", g.notas])
        messagebox.showinfo("Exportado", f"Archivo guardado en:\n{path}")
