from __future__ import annotations
import customtkinter as ctk
from datetime import date
from typing import Callable

from db import Database
from utils import (
    format_currency, format_date, mes_actual_periodo,
    mes_anterior_periodo, periodo_label, periodos_tarjeta,
    convertir_a_cop
)


class DashboardView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._build()

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(1, weight=1)

        today = date.today()
        MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        ctk.CTkLabel(header, text="Dashboard",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"{MESES[today.month - 1]} {today.year}",
                     font=ctk.CTkFont(size=14), text_color="gray").grid(row=0, column=1, sticky="w", padx=12)
        ctk.CTkButton(header, text="+ Nuevo Gasto", width=140, height=32,
                      command=lambda: self.navigate('gastos')).grid(row=0, column=2, sticky="e")

        # Budget alert bar (hidden by default)
        self.alert_bar = ctk.CTkFrame(self, fg_color="#F44336", corner_radius=8)
        self.alert_label = ctk.CTkLabel(self.alert_bar, text="", text_color="white",
                                        font=ctk.CTkFont(size=13))
        self.alert_label.pack(padx=16, pady=8)

        # Metric cards row (4 cards)
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for i in range(4):
            self.cards_frame.grid_columnconfigure(i, weight=1)

        self.metric_widgets: list[_MetricCard] = []
        labels = ["Gastado este mes", "Mes anterior", "Presupuesto usado", "Deuda en tarjetas"]
        for i, lbl in enumerate(labels):
            mc = _MetricCard(self.cards_frame, lbl)
            mc.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            self.metric_widgets.append(mc)

        # Cuotas TC panel
        self._cuotas_panel = _CuotasPanel(self)
        self._cuotas_panel.grid(row=3, column=0, sticky="ew", pady=(0, 16))

        # Bottom: recent expenses + card summaries
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="nsew")
        bottom.grid_columnconfigure(0, weight=3)
        bottom.grid_columnconfigure(1, weight=2)
        bottom.grid_rowconfigure(0, weight=1)

        self._build_recent(bottom)
        self._build_card_summary(bottom)

    def _build_recent(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Gastos recientes",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="Ver todos →", width=90, height=26, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray80"),
                      command=lambda: self.navigate('historial')).grid(row=0, column=2, sticky="e")

        self.recent_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.recent_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self.recent_scroll.grid_columnconfigure(0, weight=1)

    def _build_card_summary(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Tarjetas de crédito",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="Gestionar →", width=90, height=26, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray80"),
                      command=lambda: self.navigate('tarjetas')).grid(row=0, column=2, sticky="e")

        self.cards_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.cards_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self.cards_scroll.grid_columnconfigure(0, weight=1)

    # ─────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────

    def refresh(self, **_):
        today = date.today()
        moneda = self.db.get_config('moneda', 'COP')
        presupuesto = float(self.db.get_config('presupuesto_mensual', '3000000') or 0)

        # Totals
        total_mes = self.db.get_total_mes(today.year, today.month)
        f1, f2 = mes_anterior_periodo()
        d = __import__('datetime').datetime.strptime(f1, '%Y-%m-%d')
        total_ant = self.db.get_total_mes(d.year, d.month)

        pct = (total_mes / presupuesto * 100) if presupuesto > 0 else 0

        # Deuda tarjetas (sum of current-period balances)
        tarjetas = self.db.get_tarjetas(solo_activas=True)
        deuda_total = sum(
            self.db.get_total_tarjeta_periodo(
                t.id, __import__('utils').periodo_actual(t.dia_corte)
            )
            for t in tarjetas
        )

        # Metric cards
        self.metric_widgets[0].set_value(format_currency(total_mes, moneda), color="#2196F3")
        delta = total_mes - total_ant
        delta_text = f"{'↑' if delta >= 0 else '↓'} {format_currency(abs(delta), moneda)} vs mes ant."
        self.metric_widgets[1].set_value(
            format_currency(total_ant, moneda),
            subtitle=delta_text,
            color="#4CAF50" if delta <= 0 else "#FF9800",
        )
        pct_color = "#4CAF50" if pct < 75 else "#FF9800" if pct < 100 else "#F44336"
        self.metric_widgets[2].set_value(
            f"{pct:.1f}%",
            subtitle=f"{format_currency(total_mes, moneda)} de {format_currency(presupuesto, moneda)}",
            color=pct_color,
        )
        self.metric_widgets[3].set_value(format_currency(deuda_total, moneda), color="#9C27B0")

        # Budget alert
        if presupuesto > 0 and total_mes >= presupuesto:
            self.alert_label.configure(
                text=f"⚠  Has superado tu presupuesto mensual de {format_currency(presupuesto, moneda)}. "
                     f"Llevas {format_currency(total_mes, moneda)} ({pct:.1f}%)"
            )
            self.alert_bar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        else:
            self.alert_bar.grid_remove()

        # Recent expenses
        for w in self.recent_scroll.winfo_children():
            w.destroy()
        gastos = self.db.get_gastos_recientes(limit=15)
        if not gastos:
            ctk.CTkLabel(self.recent_scroll, text="Sin gastos registrados aún.",
                         text_color="gray").pack(pady=20)
        for g in gastos:
            _GastoRow(self.recent_scroll, g, moneda).pack(fill="x", padx=4, pady=2)

        # Cuotas TC panel
        cuotas_data = self.db.get_total_pagado_mes(today.year, today.month)
        tasas = self.db.get_all_config()
        self._cuotas_panel.update(cuotas_data, moneda, tasas)

        # Card summaries
        for w in self.cards_scroll.winfo_children():
            w.destroy()
        if not tarjetas:
            ctk.CTkLabel(self.cards_scroll, text="Sin tarjetas configuradas.",
                         text_color="gray").pack(pady=20)
        for t in tarjetas:
            _CardSummaryRow(self.cards_scroll, t, self.db, moneda).pack(fill="x", padx=4, pady=4)


# ─────────────────────────────────────────────
# Helper widgets
# ─────────────────────────────────────────────

class _MetricCard(ctk.CTkFrame):
    def __init__(self, parent, title: str):
        super().__init__(parent, corner_radius=10)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12),
                     text_color="gray").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        self.val_label = ctk.CTkLabel(self, text="—",
                                      font=ctk.CTkFont(size=20, weight="bold"))
        self.val_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 2))
        self.sub_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.sub_label.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))

    def set_value(self, value: str, subtitle: str = "", color: str = "#2196F3"):
        self.val_label.configure(text=value, text_color=color)
        self.sub_label.configure(text=subtitle)


class _GastoRow(ctk.CTkFrame):
    def __init__(self, parent, gasto, moneda: str):
        super().__init__(parent, corner_radius=6, fg_color=("gray90", "gray17"))
        self.grid_columnconfigure(1, weight=1)

        color = gasto.categoria_color or "#607D8B"
        dot = ctk.CTkLabel(self, text="●", text_color=color,
                           font=ctk.CTkFont(size=14), width=20)
        dot.grid(row=0, column=0, padx=(10, 6), pady=8)

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew")
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(info, text=gasto.descripcion,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        cat_text = gasto.categoria_nombre or "Sin categoría"
        ctk.CTkLabel(info, text=f"{cat_text} · {format_date(gasto.fecha)}",
                     font=ctk.CTkFont(size=11), text_color="gray",
                     anchor="w").grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(self, text=format_currency(gasto.monto, moneda),
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#F44336").grid(row=0, column=2, padx=(8, 12), pady=8)


class _CuotasPanel(ctk.CTkFrame):
    """Dashboard panel showing TC installment breakdown for the current month."""

    def __init__(self, parent):
        super().__init__(parent, corner_radius=10)
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Title
        ctk.CTkLabel(self, text="💳  Tarjeta de Crédito — Cuotas este mes",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=4,
                                      sticky="w", padx=16, pady=(12, 6))

        # Four sub-cards inside
        self._lbl_compras  = self._sub(1, 0, "Compras registradas TC")
        self._lbl_cuota    = self._sub(1, 1, "Cuota mensual real")
        self._lbl_ahorro   = self._sub(1, 2, "Diferido en cuotas")
        self._lbl_info     = self._sub(1, 3, "Detalle")

    def _sub(self, row, col, title) -> ctk.CTkLabel:
        f = ctk.CTkFrame(self, fg_color=("gray88", "gray20"), corner_radius=8)
        f.grid(row=row, column=col, sticky="nsew",
               padx=(12 if col == 0 else 6, 6 if col < 3 else 12),
               pady=(0, 12))
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11),
                     text_color="gray", anchor="w").grid(row=0, column=0,
                                                          sticky="w", padx=10, pady=(8, 2))
        val = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=16, weight="bold"), anchor="w")
        val.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        return val

    def update(self, data: dict, moneda: str, tasas: dict):
        total_c = data.get('total_compras', 0)
        total_q = data.get('total_cuotas',  0)
        n       = data.get('n_gastos',       0)
        n_q     = data.get('n_en_cuotas',    0)
        avg_q   = data.get('avg_cuotas',     0)
        diferido = total_c - total_q

        self._lbl_compras.configure(
            text=format_currency(total_c, moneda), text_color="#F44336")
        self._lbl_cuota.configure(
            text=format_currency(total_q, moneda), text_color="#4CAF50")
        self._lbl_ahorro.configure(
            text=format_currency(diferido, moneda),
            text_color="#2196F3" if diferido > 0 else "gray")

        if n == 0:
            info = "Sin compras TC"
        elif n_q == 0:
            info = f"{n} compra(s) · todo contado"
        else:
            info = (f"{n} compra(s)\n"
                    f"{n_q} en cuotas\n"
                    f"~{avg_q:.1f} cuotas prom.")
        self._lbl_info.configure(text=info, font=ctk.CTkFont(size=12))


class _CardSummaryRow(ctk.CTkFrame):
    def __init__(self, parent, tarjeta, db: Database, moneda: str):
        super().__init__(parent, corner_radius=8, fg_color=("gray90", "gray17"))
        self.grid_columnconfigure(0, weight=1)

        import utils as _u
        periodos = _u.periodos_tarjeta(tarjeta.dia_corte, tarjeta.dia_pago)
        total_act = db.get_total_tarjeta_periodo(tarjeta.id, periodos['periodo_actual'])

        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        name_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(name_frame, text=tarjeta.nombre,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(name_frame, text=tarjeta.banco,
                     font=ctk.CTkFont(size=11), text_color="gray",
                     anchor="e").grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(self, text=format_currency(total_act, moneda),
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#F44336").grid(row=1, column=0, sticky="w", padx=12)

        dias = periodos['dias_para_corte']
        corte_str = periodos['fecha_corte_actual'].strftime('%d/%m/%Y')
        status = f"Corte en {dias} día{'s' if dias != 1 else ''} ({corte_str})"
        status_color = "#F44336" if dias <= 3 else "#FF9800" if dias <= 7 else "gray"
        ctk.CTkLabel(self, text=status, font=ctk.CTkFont(size=11),
                     text_color=status_color).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
