from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
from typing import Callable

from db import Database
from models import Tarjeta
from utils import format_currency, periodos_tarjeta, periodo_label, format_date


class TarjetasView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Tarjetas de Crédito",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="+ Nueva Tarjeta", width=150, height=32,
                      command=self._add_card_dialog).grid(row=0, column=2, sticky="e")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

    def refresh(self, **_):
        for w in self.scroll.winfo_children():
            w.destroy()
        moneda = self.db.get_config('moneda', 'COP')
        tarjetas = self.db.get_tarjetas()
        if not tarjetas:
            ctk.CTkLabel(self.scroll, text="Sin tarjetas. Agrega una con el botón de arriba.",
                         text_color="gray").pack(pady=40)
            return
        for t in tarjetas:
            _CardPanel(self.scroll, t, self.db, moneda,
                       on_edit=self._edit_card_dialog,
                       on_delete=self._delete_card).pack(fill="x", pady=8)

    # ─────────────────────────────────────────
    # Dialogs
    # ─────────────────────────────────────────

    def _add_card_dialog(self):
        _CardFormDialog(self, self.db, on_save=lambda: self.refresh())

    def _edit_card_dialog(self, tarjeta: Tarjeta):
        _CardFormDialog(self, self.db, tarjeta=tarjeta, on_save=lambda: self.refresh())

    def _delete_card(self, tarjeta: Tarjeta):
        if messagebox.askyesno(
            "Eliminar tarjeta",
            f"¿Eliminar la tarjeta «{tarjeta.nombre}»?\n"
            "Los gastos asociados perderán su referencia de tarjeta.",
        ):
            self.db.delete_tarjeta(tarjeta.id)
            self.refresh()


# ─────────────────────────────────────────────
# Card panel widget
# ─────────────────────────────────────────────

class _CardPanel(ctk.CTkFrame):
    def __init__(self, parent, tarjeta: Tarjeta, db: Database, moneda: str,
                 on_edit, on_delete):
        super().__init__(parent, corner_radius=12)
        self.db = db
        self.tarjeta = tarjeta
        self.moneda = moneda
        self._build(on_edit, on_delete)

    def _build(self, on_edit, on_delete):
        self.grid_columnconfigure(0, weight=1)

        # ── Card header ──
        head = ctk.CTkFrame(self, fg_color=("gray80", "gray22"), corner_radius=10)
        head.pack(fill="x", padx=2, pady=2)
        head.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(head, text="💳", font=ctk.CTkFont(size=26)).grid(
            row=0, column=0, padx=14, pady=12)
        info = ctk.CTkFrame(head, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(info, text=self.tarjeta.nombre,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(info, text=f"{self.tarjeta.banco}  ·  Corte día {self.tarjeta.dia_corte}"
                                 f"  ·  Pago día {self.tarjeta.dia_pago}",
                     font=ctk.CTkFont(size=12), text_color="gray",
                     anchor="w").pack(fill="x")

        actions = ctk.CTkFrame(head, fg_color="transparent")
        actions.grid(row=0, column=2, padx=12)
        ctk.CTkButton(actions, text="Editar", width=70, height=28,
                      fg_color="transparent", border_width=1,
                      command=lambda: on_edit(self.tarjeta)).pack(pady=2)
        ctk.CTkButton(actions, text="Eliminar", width=70, height=28,
                      fg_color="transparent", border_width=1, text_color="#F44336",
                      command=lambda: on_delete(self.tarjeta)).pack(pady=2)

        # ── Billing periods via TabView ──
        tabs = ctk.CTkTabview(self, height=220)
        tabs.pack(fill="x", padx=6, pady=(4, 6))

        periodos_info = periodos_tarjeta(self.tarjeta.dia_corte, self.tarjeta.dia_pago)

        for period_key, label_suffix in [
            ('periodo_actual',  f"Este corte (cierra {periodos_info['fecha_corte_actual'].strftime('%d/%m')})"),
            ('periodo_proximo', f"Próximo corte (cierra {periodos_info['fecha_corte_proximo'].strftime('%d/%m')})"),
        ]:
            tab = tabs.add(label_suffix)
            tab.grid_columnconfigure(0, weight=1)
            periodo = periodos_info[period_key]
            total = self.db.get_total_tarjeta_periodo(self.tarjeta.id, periodo)
            gastos = self.db.get_gastos_tarjeta_periodo(self.tarjeta.id, periodo)

            summary = ctk.CTkFrame(tab, fg_color="transparent")
            summary.pack(fill="x", pady=(6, 4))
            summary.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(summary, text="Total acumulado",
                         font=ctk.CTkFont(size=12), text_color="gray").grid(
                row=0, column=0, sticky="w", padx=8)
            ctk.CTkLabel(summary, text=format_currency(total, self.moneda),
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color="#F44336").grid(row=0, column=1, sticky="e", padx=8)

            ctk.CTkLabel(summary, text=f"Fecha límite de pago: "
                                        f"{periodos_info['fecha_limite_pago'].strftime('%d/%m/%Y')}",
                         font=ctk.CTkFont(size=12), text_color="gray").grid(
                row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

            scroll = ctk.CTkScrollableFrame(tab, height=110, fg_color="transparent")
            scroll.pack(fill="x", padx=4)
            scroll.grid_columnconfigure(1, weight=1)

            if not gastos:
                ctk.CTkLabel(scroll, text="Sin gastos en este corte.", text_color="gray").pack(pady=8)
            else:
                for g in gastos:
                    row_f = ctk.CTkFrame(scroll, fg_color=("gray88", "gray18"), corner_radius=4)
                    row_f.pack(fill="x", pady=1)
                    row_f.grid_columnconfigure(1, weight=1)
                    color = g.categoria_color or "#607D8B"
                    ctk.CTkLabel(row_f, text="●", text_color=color, width=16).grid(
                        row=0, column=0, padx=(8, 4), pady=4)
                    ctk.CTkLabel(row_f, text=g.descripcion, anchor="w").grid(
                        row=0, column=1, sticky="ew", padx=2, pady=4)
                    ctk.CTkLabel(row_f, text=format_date(g.fecha),
                                 font=ctk.CTkFont(size=11), text_color="gray").grid(
                        row=0, column=2, padx=4, pady=4)
                    ctk.CTkLabel(row_f, text=format_currency(g.monto, self.moneda),
                                 text_color="#F44336").grid(row=0, column=3, padx=(4, 8), pady=4)


# ─────────────────────────────────────────────
# Card form dialog
# ─────────────────────────────────────────────

class _CardFormDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, tarjeta: Tarjeta = None, on_save=None):
        super().__init__(parent)
        self.db = db
        self.tarjeta = tarjeta
        self.on_save = on_save
        self.title("Nueva Tarjeta" if not tarjeta else "Editar Tarjeta")
        self.geometry("440x380")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        if tarjeta:
            self._load()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        def row(label, widget, r):
            ctk.CTkLabel(self, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(20, 8), pady=(10, 2))
            widget.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))

        self.nombre_var = ctk.StringVar()
        row("Nombre *", ctk.CTkEntry(self, textvariable=self.nombre_var,
                                     placeholder_text="Ej: Visa Bancolombia"), 0)

        self.banco_var = ctk.StringVar()
        row("Banco", ctk.CTkEntry(self, textvariable=self.banco_var,
                                   placeholder_text="Ej: Bancolombia"), 1)

        self.corte_var = ctk.StringVar(value="15")
        days = [str(i) for i in range(1, 29)]
        row("Día de corte *", ctk.CTkComboBox(self, values=days,
                                               variable=self.corte_var), 2)

        self.pago_var = ctk.StringVar(value="5")
        row("Día de pago *", ctk.CTkComboBox(self, values=days,
                                              variable=self.pago_var), 3)

        self.activa_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self, text="Tarjeta activa",
                        variable=self.activa_var).grid(row=4, column=1, sticky="w",
                                                       padx=(0, 20), pady=(10, 2))

        ctk.CTkButton(self, text="Guardar", command=self._save).grid(
            row=5, column=0, columnspan=2, pady=20, padx=20, sticky="ew")

    def _load(self):
        self.nombre_var.set(self.tarjeta.nombre)
        self.banco_var.set(self.tarjeta.banco)
        self.corte_var.set(str(self.tarjeta.dia_corte))
        self.pago_var.set(str(self.tarjeta.dia_pago))
        self.activa_var.set(self.tarjeta.activa)

    def _save(self):
        nombre = self.nombre_var.get().strip()
        if not nombre:
            messagebox.showerror("Error", "El nombre es obligatorio.", parent=self)
            return
        t = Tarjeta(
            id=self.tarjeta.id if self.tarjeta else None,
            nombre=nombre,
            banco=self.banco_var.get().strip(),
            dia_corte=int(self.corte_var.get()),
            dia_pago=int(self.pago_var.get()),
            activa=self.activa_var.get(),
        )
        if self.tarjeta:
            self.db.update_tarjeta(t)
        else:
            self.db.add_tarjeta(t)
        if self.on_save:
            self.on_save()
        self.destroy()
