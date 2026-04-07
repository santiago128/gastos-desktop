from __future__ import annotations
import customtkinter as ctk
from datetime import date
from tkinter import messagebox
from typing import Callable, Optional

from db import Database
from models import Gasto
from utils import (
    calcular_corte_periodo, format_currency, parse_amount,
    periodos_tarjeta, periodo_label, today_iso, PALETTE
)

METODOS = ['Efectivo', 'Tarjeta de crédito', 'Débito/Transferencia']


class GastosView(ctk.CTkFrame):
    """Add / Edit expense view."""

    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._edit_id: Optional[int] = None
        self._build()

    # ─────────────────────────────────────────
    # Build
    # ─────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        hdr.grid_columnconfigure(1, weight=1)
        self.title_label = ctk.CTkLabel(hdr, text="Nuevo Gasto",
                                        font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.grid(row=0, column=0, sticky="w")

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        form = ctk.CTkFrame(scroll)
        form.grid(row=0, column=0, sticky="ew", ipadx=8, ipady=8)
        form.grid_columnconfigure(1, weight=1)

        row = 0

        def lbl(text):
            nonlocal row
            ctk.CTkLabel(form, text=text, anchor="w",
                         font=ctk.CTkFont(size=13)).grid(
                row=row, column=0, sticky="w", padx=(16, 8), pady=(10, 2))

        def entry_row(label, widget):
            nonlocal row
            lbl(label)
            widget.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
            row += 1

        # Descripción
        self.desc_var = ctk.StringVar()
        entry_row("Descripción *", ctk.CTkEntry(form, textvariable=self.desc_var,
                                                placeholder_text="Ej: Mercado semanal"))

        # Monto
        self.monto_var = ctk.StringVar()
        entry_row("Monto (COP) *", ctk.CTkEntry(form, textvariable=self.monto_var,
                                                 placeholder_text="Ej: 150000"))

        # Fecha
        lbl("Fecha *")
        date_frame = ctk.CTkFrame(form, fg_color="transparent")
        date_frame.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        today = date.today()
        days   = [f"{i:02d}" for i in range(1, 32)]
        months = [f"{i:02d}" for i in range(1, 13)]
        years  = [str(y) for y in range(today.year - 3, today.year + 2)]

        self.day_var   = ctk.StringVar(value=f"{today.day:02d}")
        self.month_var = ctk.StringVar(value=f"{today.month:02d}")
        self.year_var  = ctk.StringVar(value=str(today.year))

        ctk.CTkComboBox(date_frame, values=days,   variable=self.day_var,   width=70).pack(side="left", padx=(0, 4))
        ctk.CTkComboBox(date_frame, values=months, variable=self.month_var, width=70).pack(side="left", padx=(0, 4))
        ctk.CTkComboBox(date_frame, values=years,  variable=self.year_var,  width=90).pack(side="left")
        row += 1

        # Categoría
        lbl("Categoría")
        cat_frame = ctk.CTkFrame(form, fg_color="transparent")
        cat_frame.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        cat_frame.grid_columnconfigure(0, weight=1)
        self.cat_var = ctk.StringVar(value="Seleccionar...")
        self.cat_combo = ctk.CTkComboBox(cat_frame, variable=self.cat_var, state="readonly")
        self.cat_combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(cat_frame, text="+ Nueva", width=80,
                      command=self._new_category).grid(row=0, column=1, padx=(8, 0))
        row += 1

        # Método de pago
        lbl("Método de pago *")
        self.metodo_var = ctk.StringVar(value=METODOS[0])
        metodo_combo = ctk.CTkComboBox(form, values=METODOS, variable=self.metodo_var,
                                       command=self._on_metodo_change, state="readonly")
        metodo_combo.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        row += 1

        # Tarjeta (shown only for credit card)
        lbl("Tarjeta")
        self.tarjeta_row_label = form.grid_slaves(row=row, column=0)
        self._tarjeta_lbl = ctk.CTkLabel(form, text="Tarjeta", anchor="w",
                                          font=ctk.CTkFont(size=13))
        self._tarjeta_lbl.grid(row=row, column=0, sticky="w", padx=(16, 8), pady=(10, 2))
        self.tarjeta_var = ctk.StringVar()
        self.tarjeta_combo = ctk.CTkComboBox(form, variable=self.tarjeta_var,
                                             state="readonly",
                                             command=self._update_corte_info)
        self.tarjeta_combo.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        self._tarjeta_row = row
        row += 1

        # Corte info (auto-calculated)
        self.corte_info = ctk.CTkLabel(form, text="", font=ctk.CTkFont(size=12),
                                       text_color="#2196F3")
        self.corte_info.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=(0, 4))
        self._corte_info_row = row
        row += 1

        # Notas
        lbl("Notas")
        self.notas_text = ctk.CTkTextbox(form, height=60)
        self.notas_text.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        row += 1

        # Buttons
        btn_frame = ctk.CTkFrame(form, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(16, 12), padx=16)
        ctk.CTkButton(btn_frame, text="Guardar Gasto", width=160,
                      command=self._save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Limpiar", width=100, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray80"),
                      command=self._clear).pack(side="left")

        self._on_metodo_change()

    # ─────────────────────────────────────────
    # Dynamic UI
    # ─────────────────────────────────────────

    def _on_metodo_change(self, *_):
        is_cc = self.metodo_var.get() == 'Tarjeta de crédito'
        state = "normal" if is_cc else "disabled"
        self.tarjeta_combo.configure(state="readonly" if is_cc else "disabled")
        self._tarjeta_lbl.configure(text_color="white" if is_cc else "gray")
        if not is_cc:
            self.corte_info.configure(text="")
        else:
            self._update_corte_info()

    def _update_corte_info(self, *_):
        if self.metodo_var.get() != 'Tarjeta de crédito':
            return
        tarjeta = self._get_selected_tarjeta()
        if not tarjeta:
            self.corte_info.configure(text="")
            return
        try:
            fecha_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
            periodo = calcular_corte_periodo(fecha_str, tarjeta.dia_corte)
            periodos = periodos_tarjeta(tarjeta.dia_corte, tarjeta.dia_pago)
            is_current = periodo == periodos['periodo_actual']
            label = "corte actual" if is_current else "próximo corte"
            corte_date = periodos['fecha_corte_actual'] if is_current else periodos['fecha_corte_proximo']
            color = "#4CAF50" if is_current else "#FF9800"
            self.corte_info.configure(
                text=f"Entra en el {label} · cierra {corte_date.strftime('%d/%m/%Y')}",
                text_color=color
            )
        except Exception:
            self.corte_info.configure(text="")

    def _get_selected_tarjeta(self):
        name = self.tarjeta_var.get()
        for t in self._tarjetas:
            if t.nombre == name:
                return t
        return None

    def _new_category(self):
        dialog = ctk.CTkInputDialog(text="Nombre de la nueva categoría:", title="Nueva Categoría")
        nombre = dialog.get_input()
        if nombre and nombre.strip():
            self.db.add_categoria(nombre.strip(), '#607D8B')
            self._load_combos()
            self.cat_var.set(nombre.strip())

    # ─────────────────────────────────────────
    # Load / Save
    # ─────────────────────────────────────────

    def _load_combos(self):
        cats = self.db.get_categorias()
        self._categorias = cats
        self.cat_combo.configure(values=[c.nombre for c in cats])

        self._tarjetas = self.db.get_tarjetas(solo_activas=True)
        t_names = [t.nombre for t in self._tarjetas]
        self.tarjeta_combo.configure(values=t_names)
        if t_names and not self.tarjeta_var.get() in t_names:
            self.tarjeta_var.set(t_names[0] if t_names else '')

    def refresh(self, edit_id: int = None, **_):
        self._load_combos()
        self._edit_id = edit_id
        if edit_id:
            self.title_label.configure(text="Editar Gasto")
            self._load_gasto(edit_id)
        else:
            self.title_label.configure(text="Nuevo Gasto")
            self._clear()

    def _load_gasto(self, gasto_id: int):
        g = self.db.get_gasto(gasto_id)
        if not g:
            return
        self.desc_var.set(g.descripcion)
        self.monto_var.set(str(int(g.monto)))
        try:
            parts = g.fecha.split('-')
            self.year_var.set(parts[0])
            self.month_var.set(parts[1])
            self.day_var.set(parts[2])
        except Exception:
            pass
        if g.categoria_nombre:
            self.cat_var.set(g.categoria_nombre)
        self.metodo_var.set(g.metodo_pago)
        self._on_metodo_change()
        if g.tarjeta_nombre:
            self.tarjeta_var.set(g.tarjeta_nombre)
        self.notas_text.delete("1.0", "end")
        self.notas_text.insert("1.0", g.notas or '')
        self._update_corte_info()

    def _save(self):
        errors = []
        desc = self.desc_var.get().strip()
        if not desc:
            errors.append("La descripción es obligatoria.")
        try:
            monto = parse_amount(self.monto_var.get())
            if monto <= 0:
                errors.append("El monto debe ser mayor a cero.")
        except Exception:
            monto = 0
            errors.append("El monto no es válido.")

        try:
            fecha_str = f"{self.year_var.get()}-{self.month_var.get()}-{self.day_var.get()}"
            from datetime import datetime
            datetime.strptime(fecha_str, '%Y-%m-%d')
        except Exception:
            errors.append("Fecha inválida.")
            fecha_str = today_iso()

        metodo = self.metodo_var.get()
        tarjeta_id = None
        corte_periodo = None
        if metodo == 'Tarjeta de crédito':
            t = self._get_selected_tarjeta()
            if not t:
                errors.append("Selecciona una tarjeta de crédito.")
            else:
                tarjeta_id = t.id
                corte_periodo = calcular_corte_periodo(fecha_str, t.dia_corte)

        # Categoría
        cat_id = None
        cat_name = self.cat_var.get()
        for c in self._categorias:
            if c.nombre == cat_name:
                cat_id = c.id
                break

        notas = self.notas_text.get("1.0", "end").strip()

        if errors:
            messagebox.showerror("Errores en el formulario", "\n".join(errors))
            return

        g = Gasto(
            id=self._edit_id,
            descripcion=desc,
            monto=monto,
            fecha=fecha_str,
            categoria_id=cat_id,
            metodo_pago=metodo,
            tarjeta_id=tarjeta_id,
            corte_periodo=corte_periodo,
            notas=notas,
        )

        if self._edit_id:
            self.db.update_gasto(g)
            messagebox.showinfo("Listo", "Gasto actualizado correctamente.")
        else:
            self.db.add_gasto(g)
            messagebox.showinfo("Listo", "Gasto registrado correctamente.")

        self._clear()
        self._edit_id = None
        self.title_label.configure(text="Nuevo Gasto")

    def _clear(self):
        self.desc_var.set('')
        self.monto_var.set('')
        today = date.today()
        self.day_var.set(f"{today.day:02d}")
        self.month_var.set(f"{today.month:02d}")
        self.year_var.set(str(today.year))
        self.cat_var.set("Seleccionar...")
        self.metodo_var.set(METODOS[0])
        self.notas_text.delete("1.0", "end")
        self.corte_info.configure(text="")
        self._on_metodo_change()
