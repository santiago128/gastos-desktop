from __future__ import annotations
import customtkinter as ctk
import os
from tkinter import messagebox, filedialog
from typing import Callable

from db import Database


class ConfigView(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable, on_theme_change=None):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self.on_theme_change = on_theme_change
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Configuración",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # ── Personal ──
        self._section(scroll, "Información personal", 0)
        form1 = ctk.CTkFrame(scroll)
        form1.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        form1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form1, text="Nombre de usuario",
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 8))
        self.nombre_var = ctk.StringVar()
        ctk.CTkEntry(form1, textvariable=self.nombre_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 16), pady=(12, 8))

        ctk.CTkLabel(form1, text="Moneda", anchor="w").grid(
            row=1, column=0, sticky="w", padx=(16, 8), pady=8)
        self.moneda_var = ctk.StringVar(value='COP')
        ctk.CTkComboBox(form1, values=['COP', 'USD', 'EUR', 'MXN'],
                        variable=self.moneda_var, state="readonly",
                        width=120).grid(row=1, column=1, sticky="w", padx=(0, 16), pady=8)

        # ── Budget ──
        self._section(scroll, "Presupuesto", 2)
        form2 = ctk.CTkFrame(scroll)
        form2.grid(row=3, column=0, sticky="ew", pady=(0, 16))
        form2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form2, text="Límite mensual",
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 8))
        self.presupuesto_var = ctk.StringVar()
        ctk.CTkEntry(form2, textvariable=self.presupuesto_var,
                     placeholder_text="Ej: 3000000").grid(
            row=0, column=1, sticky="ew", padx=(0, 16), pady=(12, 8))
        ctk.CTkLabel(form2, text="(0 = sin límite)",
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 8))

        # ── Exchange rates ──
        self._section(scroll, "Tasas de cambio → COP", 4)
        form_fx = ctk.CTkFrame(scroll)
        form_fx.grid(row=5, column=0, sticky="ew", pady=(0, 16))
        form_fx.grid_columnconfigure(1, weight=1)

        fx_fields = [
            ("USD → COP", "tasa_usd_cop", "Ej: 4200"),
            ("EUR → COP", "tasa_eur_cop", "Ej: 4600"),
            ("GBP → COP", "tasa_gbp_cop", "Ej: 5300"),
        ]
        self._fx_vars: dict[str, ctk.StringVar] = {}
        for i, (label, key, ph) in enumerate(fx_fields):
            ctk.CTkLabel(form_fx, text=label, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(16, 8), pady=(10 if i == 0 else 4, 4))
            var = ctk.StringVar()
            self._fx_vars[key] = var
            ctk.CTkEntry(form_fx, textvariable=var, placeholder_text=ph, width=120).grid(
                row=i, column=1, sticky="w", padx=(0, 16), pady=(10 if i == 0 else 4, 4))

        # ── Appearance ──
        self._section(scroll, "Apariencia", 8)
        form3 = ctk.CTkFrame(scroll)
        form3.grid(row=9, column=0, sticky="ew", pady=(0, 16))
        form3.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form3, text="Tema", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 8))
        self.tema_var = ctk.StringVar(value='dark')
        ctk.CTkSegmentedButton(form3, values=['dark', 'light', 'system'],
                                variable=self.tema_var).grid(
            row=0, column=1, sticky="w", padx=(0, 16), pady=(12, 8))

        # ── Data management ──
        self._section(scroll, "Datos", 10)
        data_frame = ctk.CTkFrame(scroll)
        data_frame.grid(row=11, column=0, sticky="ew", pady=(0, 16))

        ctk.CTkLabel(data_frame, text="Base de datos",
                     anchor="w",
                     font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 6))
        self.db_path_label = ctk.CTkLabel(data_frame, text=self.db.db_path,
                                          font=ctk.CTkFont(size=11),
                                          text_color="gray", anchor="w", wraplength=480)
        self.db_path_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        btn_row = ctk.CTkFrame(data_frame, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkButton(btn_row, text="Hacer backup", width=130,
                      command=self._backup).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Abrir carpeta", width=130, fg_color="transparent",
                      border_width=1, text_color=("gray20", "gray80"),
                      command=self._open_folder).pack(side="left")

        # Save button
        ctk.CTkButton(scroll, text="Guardar cambios", height=40,
                      command=self._save).grid(row=12, column=0, sticky="ew",
                                               padx=0, pady=(8, 24))

    @staticmethod
    def _section(parent, title: str, row: int):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").grid(row=row, column=0, sticky="w", pady=(12, 4))

    def refresh(self, **_):
        cfg = self.db.get_all_config()
        self.nombre_var.set(cfg.get('nombre_usuario', ''))
        self.moneda_var.set(cfg.get('moneda', 'COP'))
        self.presupuesto_var.set(cfg.get('presupuesto_mensual', '3000000'))
        self.tema_var.set(cfg.get('tema', 'dark'))
        for key, var in self._fx_vars.items():
            var.set(cfg.get(key, ''))

    def _save(self):
        try:
            presupuesto = float(self.presupuesto_var.get().replace(',', '').strip() or '0')
        except ValueError:
            messagebox.showerror("Error", "El presupuesto mensual debe ser un número.")
            return

        # Validate exchange rates
        for key, var in self._fx_vars.items():
            val = var.get().strip()
            if val:
                try:
                    float(val)
                except ValueError:
                    messagebox.showerror("Error", f"Tasa de cambio inválida: {val}")
                    return

        self.db.set_config('nombre_usuario', self.nombre_var.get().strip())
        self.db.set_config('moneda', self.moneda_var.get())
        self.db.set_config('presupuesto_mensual', str(presupuesto))
        tema = self.tema_var.get()
        self.db.set_config('tema', tema)
        for key, var in self._fx_vars.items():
            val = var.get().strip()
            if val:
                self.db.set_config(key, val)

        ctk.set_appearance_mode(tema)
        if self.on_theme_change:
            self.on_theme_change(tema)

        messagebox.showinfo("Guardado", "Configuración guardada correctamente.")

    def _backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".db",
            initialfile="gastos_backup.db",
            filetypes=[("SQLite DB", "*.db"), ("Todos", "*.*")],
        )
        if path:
            self.db.backup(path)
            messagebox.showinfo("Backup", f"Backup guardado en:\n{path}")

    def _open_folder(self):
        folder = os.path.dirname(self.db.db_path)
        os.startfile(folder)
