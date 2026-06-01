"""
views/deudas.py — Módulo para registrar y gestionar dinero que te deben.

Funcionalidades:
  • Registrar una deuda: quién debe, cuánto, cuándo y para qué
  • Listar deudas con filtro por estado (todas / pendiente / parcial / pagado)
  • Registrar pagos parciales o totales
  • Editar o eliminar registros
  • Panel de resumen con totales
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import customtkinter as ctk

from db import Database
from utils import format_currency, format_date, today_iso

# ── Paleta ───────────────────────────────────────────────────────────────────
_GREEN  = "#4CAF50"
_GREEN_D = "#2E7D32"
_BLUE   = "#2196F3"
_BLUE_D = "#1565C0"
_RED    = "#F44336"
_ORANGE = "#FF9800"
_GREY   = "#607D8B"

_ESTADO_CFG = {
    "pendiente": {"label": "⏳  Pendiente", "color": _ORANGE,  "bg": "#FFF3E0"},
    "parcial":   {"label": "🔄  Parcial",   "color": _BLUE,    "bg": "#E3F2FD"},
    "pagado":    {"label": "✅  Pagado",    "color": _GREEN,   "bg": "#E8F5E9"},
}

MONEDAS = ["COP", "USD", "EUR", "GBP"]


# ─────────────────────────────────────────────────────────────────────────────
# Diálogo: nueva / editar deuda
# ─────────────────────────────────────────────────────────────────────────────

class _DeudaDialog(ctk.CTkToplevel):
    """Modal para crear o editar una deuda."""

    def __init__(self, parent, on_save: Callable, deuda: dict = None):
        super().__init__(parent)
        self.on_save = on_save
        self.deuda   = deuda   # None → nueva

        self.title("Nueva deuda" if deuda is None else "Editar deuda")
        self.geometry("480x500")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        self._build()
        if deuda:
            self._fill(deuda)

    def _build(self):
        pad = {"padx": 20, "pady": (6, 2)}

        ctk.CTkLabel(self, text="¿Quién te debe?",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", **pad)
        self.e_deudor = ctk.CTkEntry(self, placeholder_text="Nombre o alias", width=420)
        self.e_deudor.pack(padx=20, pady=(0, 8))

        ctk.CTkLabel(self, text="Descripción / concepto",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", **pad)
        self.e_desc = ctk.CTkEntry(self, placeholder_text="Por qué te debe…", width=420)
        self.e_desc.pack(padx=20, pady=(0, 8))

        # Monto + moneda en la misma fila
        ctk.CTkLabel(self, text="Monto",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", **pad)
        row_m = ctk.CTkFrame(self, fg_color="transparent")
        row_m.pack(padx=20, pady=(0, 8), fill="x")
        self.e_monto = ctk.CTkEntry(row_m, placeholder_text="0", width=300)
        self.e_monto.pack(side="left", padx=(0, 8))
        self.sel_moneda = ctk.StringVar(value="COP")
        ctk.CTkOptionMenu(row_m, values=MONEDAS, variable=self.sel_moneda,
                          width=110).pack(side="left")

        ctk.CTkLabel(self, text="Fecha (préstamo o acuerdo)",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", **pad)
        self.e_fecha = ctk.CTkEntry(self, placeholder_text="YYYY-MM-DD", width=420)
        self.e_fecha.insert(0, today_iso())
        self.e_fecha.pack(padx=20, pady=(0, 8))

        ctk.CTkLabel(self, text="Notas (opcional)",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", **pad)
        self.e_notas = ctk.CTkTextbox(self, height=70, width=420)
        self.e_notas.pack(padx=20, pady=(0, 12))

        # Botones
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=20, pady=(0, 16), fill="x")
        ctk.CTkButton(btn_row, text="Cancelar", width=120,
                      fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray80"),
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="💾  Guardar", width=140,
                      fg_color=_GREEN, hover_color=_GREEN_D,
                      command=self._save).pack(side="right")

    def _fill(self, d: dict):
        self.e_deudor.insert(0, d["deudor"])
        self.e_desc.insert(0, d["descripcion"])
        self.e_monto.insert(0, str(d["monto"]))
        self.sel_moneda.set(d.get("moneda", "COP"))
        self.e_fecha.delete(0, "end")
        self.e_fecha.insert(0, d["fecha"])
        if d.get("notas"):
            self.e_notas.insert("0.0", d["notas"])

    def _save(self):
        deudor = self.e_deudor.get().strip()
        desc   = self.e_desc.get().strip()
        monto_s = self.e_monto.get().strip().replace(",", "").replace(".", "")
        fecha  = self.e_fecha.get().strip()
        notas  = self.e_notas.get("0.0", "end").strip()
        moneda = self.sel_moneda.get()

        if not deudor:
            self._shake(self.e_deudor); return
        if not desc:
            self._shake(self.e_desc); return
        try:
            monto = float(monto_s)
            assert monto > 0
        except Exception:
            self._shake(self.e_monto); return
        try:
            date.fromisoformat(fecha)
        except ValueError:
            self._shake(self.e_fecha); return

        self.on_save(deudor=deudor, descripcion=desc, monto=monto,
                     fecha=fecha, notas=notas, moneda=moneda)
        self.destroy()

    @staticmethod
    def _shake(widget):
        orig = widget.cget("border_color") if hasattr(widget, "cget") else None
        widget.configure(border_color=_RED)
        widget.after(600, lambda: widget.configure(
            border_color=("gray65", "gray40") if orig is None else orig))


# ─────────────────────────────────────────────────────────────────────────────
# Diálogo: registrar pago
# ─────────────────────────────────────────────────────────────────────────────

class _PagoDialog(ctk.CTkToplevel):
    def __init__(self, parent, deuda: dict, on_save: Callable):
        super().__init__(parent)
        self.deuda   = deuda
        self.on_save = on_save

        pendiente = deuda["monto"] - deuda["monto_pagado"]
        moneda    = deuda.get("moneda", "COP")

        self.title("Registrar pago")
        self.geometry("400x300")
        self.resizable(False, False)
        self.grab_set()
        self.focus_force()

        pad = {"padx": 24, "pady": (8, 2)}

        ctk.CTkLabel(self,
                     text=f"Deudor: {deuda['deudor']}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkLabel(self,
                     text=f"Pendiente: {format_currency(pendiente, moneda)}",
                     font=ctk.CTkFont(size=12), text_color=_ORANGE).pack(anchor="w", **pad)

        ctk.CTkLabel(self, text="Monto a registrar como pagado",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=24, pady=(16, 2))
        self.e_monto = ctk.CTkEntry(self, placeholder_text="0", width=340)
        self.e_monto.insert(0, str(pendiente))
        self.e_monto.pack(padx=24, pady=(0, 8))

        ctk.CTkLabel(self, text="Fecha de pago",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=24, pady=(4, 2))
        self.e_fecha = ctk.CTkEntry(self, placeholder_text="YYYY-MM-DD", width=340)
        self.e_fecha.insert(0, today_iso())
        self.e_fecha.pack(padx=24, pady=(0, 16))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=24, fill="x")
        ctk.CTkButton(btn_row, text="Cancelar", width=110,
                      fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray80"),
                      command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="✅  Confirmar pago", width=160,
                      fg_color=_GREEN, hover_color=_GREEN_D,
                      command=self._save).pack(side="right")

    def _save(self):
        try:
            monto = float(self.e_monto.get().strip().replace(",", "").replace(".", ""))
            assert monto > 0
        except Exception:
            self.e_monto.configure(border_color=_RED)
            return
        try:
            fecha = self.e_fecha.get().strip()
            date.fromisoformat(fecha)
        except ValueError:
            self.e_fecha.configure(border_color=_RED)
            return
        self.on_save(monto_pago=monto, fecha_pago=fecha)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Vista principal
# ─────────────────────────────────────────────────────────────────────────────

class DeudasView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db       = db
        self.navigate = navigate
        self._filtro  = "todas"   # todas | pendiente | parcial | pagado
        self._build()

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Encabezado ──
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="💸  Dinero que me deben",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w")

        ctk.CTkButton(hdr, text="➕  Registrar deuda", width=160, height=34,
                      fg_color=_GREEN, hover_color=_GREEN_D,
                      command=self._nueva_deuda).grid(
            row=0, column=2, sticky="e")

        # ── Panel de resumen ──
        self._summary_frame = ctk.CTkFrame(self, corner_radius=10,
                                           fg_color=("gray88", "gray18"))
        self._summary_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # ── Filtros + lista ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # Filtro chips
        filter_row = ctk.CTkFrame(body, fg_color="transparent")
        filter_row.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._filter_btns: dict[str, ctk.CTkButton] = {}
        opciones = [
            ("todas",     "📋  Todas"),
            ("pendiente", "⏳  Pendientes"),
            ("parcial",   "🔄  Parciales"),
            ("pagado",    "✅  Pagadas"),
        ]
        for key, lbl in opciones:
            btn = ctk.CTkButton(
                filter_row, text=lbl, width=110, height=30,
                corner_radius=16,
                fg_color=("gray78", "gray28"),
                hover_color=("gray70", "gray35"),
                font=ctk.CTkFont(size=11),
                command=lambda k=key: self._set_filtro(k),
            )
            btn.pack(side="left", padx=3)
            self._filter_btns[key] = btn

        # Lista scrollable
        self._scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

    # ─────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────

    def refresh(self, **_):
        self._render_summary()
        self._render_list()
        self._update_filter_btns()

    def _set_filtro(self, key: str):
        self._filtro = key
        self._render_list()
        self._update_filter_btns()

    def _update_filter_btns(self):
        for key, btn in self._filter_btns.items():
            if key == self._filtro:
                btn.configure(fg_color=_BLUE, text_color="white",
                              font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color=("gray78", "gray28"),
                              text_color=("gray20", "gray80"),
                              font=ctk.CTkFont(size=11))

    # ─────────────────────────────────────────
    # Summary panel
    # ─────────────────────────────────────────

    def _render_summary(self):
        for w in self._summary_frame.winfo_children():
            w.destroy()

        res    = self.db.get_resumen_deudas()
        moneda = self.db.get_config("moneda", "COP")

        cards = [
            ("💰  Total prestado",  res["total_monto"],    _BLUE,   _BLUE_D),
            ("✅  Recuperado",      res["total_pagado"],   _GREEN,  _GREEN_D),
            ("⏳  Pendiente",       res["total_pendiente"], _ORANGE, "#E65100"),
        ]

        self._summary_frame.grid_columnconfigure((0, 1, 2), weight=1)
        for col, (label, valor, fg, hover) in enumerate(cards):
            card = ctk.CTkFrame(self._summary_frame, corner_radius=8,
                                fg_color=("gray92", "gray22"))
            card.grid(row=0, column=col, padx=8, pady=10, sticky="ew")
            ctk.CTkLabel(card, text=label,
                         font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(10, 2))
            ctk.CTkLabel(card, text=format_currency(valor, moneda),
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color=fg).pack(pady=(0, 10))

    # ─────────────────────────────────────────
    # Lista de deudas
    # ─────────────────────────────────────────

    def _render_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        estado_q = None if self._filtro == "todas" else self._filtro
        deudas   = self.db.get_deudas(estado=estado_q)
        moneda   = self.db.get_config("moneda", "COP")

        if not deudas:
            ctk.CTkLabel(
                self._scroll,
                text="No hay deudas registradas." if self._filtro == "todas"
                     else f"No hay deudas con estado «{self._filtro}».",
                text_color="gray", font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, pady=40)
            return

        for i, d in enumerate(deudas):
            self._build_card(d, i, moneda)

    def _build_card(self, d: dict, idx: int, moneda: str):
        est_cfg   = _ESTADO_CFG.get(d["estado"], _ESTADO_CFG["pendiente"])
        pendiente = d["monto"] - d["monto_pagado"]
        mon_d     = d.get("moneda", "COP")

        card = ctk.CTkFrame(self._scroll, corner_radius=10,
                            fg_color=("gray90", "gray20"))
        card.grid(row=idx, column=0, sticky="ew", pady=4, padx=2)
        card.grid_columnconfigure(1, weight=1)

        # ── Columna izquierda: badge de estado ──
        badge = ctk.CTkFrame(card, corner_radius=8, width=14,
                             fg_color=est_cfg["color"])
        badge.grid(row=0, column=0, rowspan=3, padx=(10, 8), pady=10, sticky="ns")

        # ── Nombre + descripción ──
        ctk.CTkLabel(card, text=d["deudor"],
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(10, 0))
        ctk.CTkLabel(card, text=d["descripcion"],
                     font=ctk.CTkFont(size=11), text_color="gray",
                     anchor="w").grid(row=1, column=1, sticky="w", padx=(0, 8))

        # Fecha y notas
        meta_parts = [f"📅 {format_date(d['fecha'])}"]
        if d.get("notas"):
            meta_parts.append(f"📝 {d['notas'][:60]}{'…' if len(d['notas'])>60 else ''}")
        ctk.CTkLabel(card, text="   ".join(meta_parts),
                     font=ctk.CTkFont(size=10), text_color="gray",
                     anchor="w").grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(2, 10))

        # ── Columna derecha: montos + estado + acciones ──
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=2, rowspan=3, padx=(0, 12), pady=10, sticky="ns")

        # Monto total
        ctk.CTkLabel(right,
                     text=format_currency(d["monto"], mon_d),
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=_RED if d["estado"] != "pagado" else _GREEN,
                     anchor="e").pack(anchor="e")

        # Pendiente / pagado
        if d["estado"] == "pagado":
            ctk.CTkLabel(right,
                         text=f"✅ Pagado el {format_date(d['fecha_pago'] or '')}",
                         font=ctk.CTkFont(size=10), text_color=_GREEN,
                         anchor="e").pack(anchor="e")
        else:
            if d["monto_pagado"] > 0:
                ctk.CTkLabel(right,
                             text=f"Pagado: {format_currency(d['monto_pagado'], mon_d)}",
                             font=ctk.CTkFont(size=10), text_color=_BLUE,
                             anchor="e").pack(anchor="e")
            ctk.CTkLabel(right,
                         text=f"Pendiente: {format_currency(pendiente, mon_d)}",
                         font=ctk.CTkFont(size=10), text_color=_ORANGE,
                         anchor="e").pack(anchor="e")

        # Chip de estado
        ctk.CTkLabel(right, text=est_cfg["label"],
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=est_cfg["color"]).pack(anchor="e", pady=(4, 0))

        # Botones de acción
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(anchor="e", pady=(6, 0))

        if d["estado"] != "pagado":
            ctk.CTkButton(
                btn_row, text="💵 Pago", width=78, height=26,
                fg_color=_GREEN, hover_color=_GREEN_D,
                font=ctk.CTkFont(size=11),
                command=lambda _d=d: self._registrar_pago(_d),
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_row, text="✏️", width=34, height=26,
            fg_color="transparent", border_width=1,
            text_color=("gray20", "gray80"),
            font=ctk.CTkFont(size=11),
            command=lambda _d=d: self._editar_deuda(_d),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_row, text="🗑", width=34, height=26,
            fg_color="transparent", border_width=1,
            text_color=_RED,
            font=ctk.CTkFont(size=11),
            command=lambda _d=d: self._eliminar_deuda(_d),
        ).pack(side="left", padx=2)

    # ─────────────────────────────────────────
    # Acciones
    # ─────────────────────────────────────────

    def _nueva_deuda(self):
        def _save(deudor, descripcion, monto, fecha, notas, moneda):
            self.db.add_deuda(deudor, descripcion, monto, fecha, notas, moneda)
            self.refresh()

        _DeudaDialog(self, on_save=_save)

    def _editar_deuda(self, d: dict):
        def _save(deudor, descripcion, monto, fecha, notas, moneda):
            self.db.update_deuda(d["id"], deudor, descripcion, monto,
                                 fecha, notas, moneda)
            self.refresh()

        _DeudaDialog(self, on_save=_save, deuda=d)

    def _registrar_pago(self, d: dict):
        def _save(monto_pago, fecha_pago):
            self.db.registrar_pago_deuda(d["id"], monto_pago, fecha_pago)
            self.refresh()

        _PagoDialog(self, deuda=d, on_save=_save)

    def _eliminar_deuda(self, d: dict):
        from tkinter import messagebox
        if messagebox.askyesno(
            "Eliminar deuda",
            f"¿Eliminar la deuda de {d['deudor']} por "
            f"{format_currency(d['monto'], d.get('moneda','COP'))}?\n\n"
            "Esta acción no se puede deshacer.",
        ):
            self.db.delete_deuda(d["id"])
            self.refresh()
