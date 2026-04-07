from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
from typing import Callable

from db import Database
from models import Categoria
from utils import PALETTE


class CategoriasView(ctk.CTkFrame):
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
        ctk.CTkLabel(hdr, text="Categorías",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="+ Nueva Categoría", width=160, height=32,
                      command=self._add_dialog).grid(row=0, column=2, sticky="e")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

    def refresh(self, **_):
        for w in self.scroll.winfo_children():
            w.destroy()
        cats = self.db.get_categorias()
        if not cats:
            ctk.CTkLabel(self.scroll, text="Sin categorías.", text_color="gray").pack(pady=40)
            return
        for c in cats:
            count = self.db.categoria_expense_count(c.id)
            _CatRow(self.scroll, c, count,
                    on_edit=lambda cat=c: self._edit_dialog(cat),
                    on_delete=lambda cat=c: self._delete(cat)).pack(fill="x", pady=3)

    def _add_dialog(self):
        _CatFormDialog(self, self.db, on_save=lambda: self.refresh())

    def _edit_dialog(self, cat: Categoria):
        _CatFormDialog(self, self.db, cat=cat, on_save=lambda: self.refresh())

    def _delete(self, cat: Categoria):
        count = self.db.categoria_expense_count(cat.id)
        msg = f"¿Eliminar la categoría «{cat.nombre}»?"
        if count > 0:
            msg += f"\n\nTiene {count} gasto(s) asociado(s) que quedarán sin categoría."
        if messagebox.askyesno("Confirmar", msg):
            other_cats = [c for c in self.db.get_categorias() if c.id != cat.id]
            reassign = other_cats[0].id if other_cats and count > 0 else None
            self.db.delete_categoria(cat.id, reassign_to=reassign)
            self.refresh()


class _CatRow(ctk.CTkFrame):
    def __init__(self, parent, cat: Categoria, count: int, on_edit, on_delete):
        super().__init__(parent, corner_radius=8, fg_color=("gray90", "gray17"))
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="●", text_color=cat.color,
                     font=ctk.CTkFont(size=22), width=36).grid(
            row=0, column=0, padx=(12, 6), pady=10)
        ctk.CTkLabel(self, text=cat.nombre,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="ew", pady=10)
        ctk.CTkLabel(self, text=f"{count} gasto{'s' if count != 1 else ''}",
                     font=ctk.CTkFont(size=12), text_color="gray").grid(
            row=0, column=2, padx=12, pady=10)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=0, column=3, padx=(0, 12))
        ctk.CTkButton(btns, text="Editar", width=70, height=28,
                      fg_color="transparent", border_width=1,
                      command=on_edit).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Eliminar", width=75, height=28,
                      fg_color="transparent", border_width=1,
                      text_color="#F44336",
                      command=on_delete).pack(side="left", padx=2)


class _CatFormDialog(ctk.CTkToplevel):
    def __init__(self, parent, db: Database, cat: Categoria = None, on_save=None):
        super().__init__(parent)
        self.db = db
        self.cat = cat
        self.on_save = on_save
        self.title("Nueva Categoría" if not cat else "Editar Categoría")
        self.geometry("380x300")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        if cat:
            self._load()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Nombre *", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(20, 8), pady=(20, 4))
        self.nombre_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self.nombre_var,
                     placeholder_text="Ej: Salud").grid(
            row=0, column=1, sticky="ew", padx=(0, 20), pady=(20, 4))

        ctk.CTkLabel(self, text="Color", anchor="w").grid(
            row=1, column=0, sticky="w", padx=(20, 8), pady=(10, 4))
        self.selected_color = ctk.StringVar(value='#2196F3')
        color_frame = ctk.CTkScrollableFrame(self, height=100, orientation="horizontal",
                                              fg_color="transparent")
        color_frame.grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=(10, 4))

        self._color_btns: list[ctk.CTkButton] = []
        for color in PALETTE:
            btn = ctk.CTkButton(color_frame, text="", width=32, height=32,
                                corner_radius=16,
                                fg_color=color, hover_color=color,
                                command=lambda c=color: self._pick_color(c))
            btn.pack(side="left", padx=3)
            self._color_btns.append(btn)

        self.preview = ctk.CTkLabel(self, text="● Vista previa",
                                    font=ctk.CTkFont(size=14),
                                    text_color=self.selected_color.get())
        self.preview.grid(row=2, column=0, columnspan=2, pady=(4, 12))

        ctk.CTkButton(self, text="Guardar", command=self._save).grid(
            row=3, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

    def _pick_color(self, color: str):
        self.selected_color.set(color)
        self.preview.configure(text_color=color)

    def _load(self):
        self.nombre_var.set(self.cat.nombre)
        self.selected_color.set(self.cat.color)
        self.preview.configure(text_color=self.cat.color)

    def _save(self):
        nombre = self.nombre_var.get().strip()
        if not nombre:
            messagebox.showerror("Error", "El nombre es obligatorio.", parent=self)
            return
        color = self.selected_color.get()
        if self.cat:
            self.db.update_categoria(self.cat.id, nombre, color)
        else:
            self.db.add_categoria(nombre, color)
        if self.on_save:
            self.on_save()
        self.destroy()
