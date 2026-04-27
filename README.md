# 💰 GastosApp — Control Personal de Gastos

Aplicación de escritorio para **Windows** que permite registrar, visualizar y analizar gastos personales. Construida con Python + CustomTkinter, base de datos SQLite local, gráficas interactivas con Matplotlib y exportación a CSV/PDF.

---

## Tabla de contenidos

1. [Características](#características)
2. [Capturas de pantalla](#capturas-de-pantalla)
3. [Requisitos](#requisitos)
4. [Instalación y ejecución](#instalación-y-ejecución)
5. [Estructura del proyecto](#estructura-del-proyecto)
6. [Arquitectura](#arquitectura)
7. [Base de datos](#base-de-datos)
8. [Configuración](#configuración)
9. [Construir el ejecutable](#construir-el-ejecutable)
10. [Guía de contribución](#guía-de-contribución)

---

## Características

| Módulo | Funcionalidades |
|---|---|
| **Dashboard** | Resumen del mes actual: total gastado, presupuesto, categorías principales, gastos recientes |
| **Nuevo Gasto** | Registro con descripción, monto, fecha, categoría, método de pago, tarjeta, cuotas, moneda y notas |
| **Historial** | Tabla paginada con filtros por mes/año/categoría/método/búsqueda; ordenación por cualquier columna; edición y eliminación |
| **Tarjetas** | CRUD de tarjetas de crédito con día de corte y día de pago; cálculo automático del período vigente |
| **Reportes** | Barras mensuales + dona por categoría interactivos; tendencia anual; comparativo 3 meses; exportar PDF y CSV |
| **Categorías** | CRUD con selector de color; reasignación de gastos al eliminar |
| **Configuración** | Nombre de usuario, moneda base, presupuesto mensual, tasas de cambio (USD/EUR/GBP → COP), tema dark/light |

**Monedas soportadas:** COP · USD · EUR · GBP  
**Temas:** Dark (predeterminado) · Light  
**Exportación:** PDF profesional (ReportLab) con portada, métricas, gráficas y tabla detallada; CSV con todos los campos

---

##Capturas de pantalla

<img width="1398" height="847" alt="image" src="https://github.com/user-attachments/assets/e958e33f-a1f2-4e4c-8c90-a32b4e754687" />
<img width="1395" height="844" alt="Captura de pantalla 2026-04-26 230416" src="https://github.com/user-attachments/assets/9a9ca225-bf13-483a-a76b-14256063a3de" />
<img width="1395" height="848" alt="Captura de pantalla 2026-04-26 230433" src="https://github.com/user-attachments/assets/5313a142-37ae-464d-9531-31ddad757537" />
<img width="1395" height="840" alt="Captura de pantalla 2026-04-26 230444" src="https://github.com/user-attachments/assets/4034991b-f5e0-465b-86d0-8761336e42f1" />
<img width="1398" height="844" alt="Captura de pantalla 2026-04-26 230629" src="https://github.com/user-attachments/assets/f6d5a944-9a39-4fc6-8667-18cca259e5e8" />
<img width="1394" height="847" alt="Captura de pantalla 2026-04-26 230539" src="https://github.com/user-attachments/assets/ca5118ae-fa7a-47c9-84f9-6bab0c5b329e" />

---

## Requisitos

| Requisito | Versión mínima |
|---|---|
| Python | 3.10 |
| customtkinter | 5.2.0 |
| matplotlib | 3.7.0 |
| Pillow | 10.0.0 |
| reportlab | 4.0.0 |

> **Solo Windows.** CustomTkinter + TkAgg funcionan en macOS y Linux, pero el ejecutable compilado con PyInstaller es específico de plataforma.

---

## Instalación y ejecución

### 1 — Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/gastos-desktop.git
cd gastos-desktop
```

### 2 — Crear entorno virtual (recomendado)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3 — Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4 — Ejecutar

```bash
python main.py
```

La primera vez que se ejecuta, la app crea automáticamente la base de datos en:

```
C:\Users\<TU_USUARIO>\.gastos_app\gastos.db
```

y la puebla con categorías predeterminadas, 3 tarjetas de ejemplo y gastos de muestra para los últimos 2 meses.

---

## Estructura del proyecto

```
gastos-desktop/
│
├── main.py              # Punto de entrada — arranca GastosApp
├── app.py               # Ventana principal, sidebar de navegación, sistema navigate()
├── db.py                # Capa de datos — clase Database (SQLite)
├── models.py            # Dataclasses: Gasto, Tarjeta, Categoria
├── utils.py             # Helpers: formato de moneda/fecha, lógica de períodos de corte
├── requirements.txt     # Dependencias Python
│
└── views/               # Una clase CTkFrame por pantalla
    ├── __init__.py
    ├── dashboard.py     # Vista Dashboard
    ├── gastos.py        # Formulario agregar/editar gasto
    ├── historial.py     # Tabla de historial con filtros
    ├── tarjetas.py      # Gestión de tarjetas de crédito
    ├── reportes.py      # Gráficas interactivas + exportación
    ├── categorias.py    # CRUD de categorías
    └── config_view.py   # Pantalla de configuración
```

### Archivos que NO se versionan (`.gitignore`)

- `__pycache__/` y archivos `.pyc`
- `.venv/` — entorno virtual
- `dist/` y `build/` — artefactos de PyInstaller
- `*.spec` — archivos de build de PyInstaller
- `*.db` — bases de datos locales (los datos son personales)

---

## Arquitectura

### Sistema de navegación

`app.py` implementa un router de vistas basado en un diccionario. Cada vista se crea **una sola vez** (lazy) y se muestra/oculta con `grid()` / `grid_remove()`:

```python
# Navegar a una vista
self.navigate('historial')

# Navegar con parámetros (ej: abrir editor de un gasto desde historial)
self.navigate('gastos', edit_id=42, from_view='historial')
```

Los `kwargs` se pasan al método `refresh(**kwargs)` de la vista de destino, diferido un tick con `after(0, ...)` para que Tk pinte el frame primero.

### Optimizaciones de rendimiento en Historial

- **Widget cache** — las filas de la tabla se crean una sola vez (`_make_row`) y se reutilizan en renders sucesivos.
- **Dirty-check por fila** — cada fila almacena una tupla `_key` con todos sus datos; si la clave no cambia, se omiten todos los `.configure()`.
- **Render incremental** — las primeras 30 filas se pintan de inmediato; el resto se procesa en batches via `after(0, ...)`. Un contador de generación (`_render_gen`) cancela batches obsoletos.

### Lógica de períodos de corte (tarjetas)

Definida en `utils.py`:

```
fecha.day < dia_corte  → gasto pertenece al período del mes actual
fecha.day >= dia_corte → gasto pertenece al período del mes siguiente
```

---

## Base de datos

**Ubicación:** `~/.gastos_app/gastos.db`  
**Motor:** SQLite 3 · WAL mode · foreign keys ON

### Esquema

```sql
-- Categorías de gasto
CREATE TABLE categorias (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT    NOT NULL UNIQUE,
    color  TEXT    NOT NULL DEFAULT '#2196F3'   -- color hex para la UI
);

-- Tarjetas de crédito
CREATE TABLE tarjetas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT    NOT NULL,
    banco     TEXT    NOT NULL DEFAULT '',
    dia_corte INTEGER NOT NULL,   -- día del mes en que cierra el período
    dia_pago  INTEGER NOT NULL,   -- día límite de pago del mes siguiente
    activa    INTEGER NOT NULL DEFAULT 1
);

-- Gastos
CREATE TABLE gastos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion   TEXT    NOT NULL,
    monto         REAL    NOT NULL,
    fecha         TEXT    NOT NULL,              -- 'YYYY-MM-DD'
    categoria_id  INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
    metodo_pago   TEXT    NOT NULL,              -- 'Efectivo' | 'Débito/Transferencia' | 'Tarjeta de crédito'
    tarjeta_id    INTEGER REFERENCES tarjetas(id) ON DELETE SET NULL,
    corte_periodo TEXT,                          -- 'YYYY-MM' del período de corte
    notas         TEXT    NOT NULL DEFAULT '',
    cuotas        INTEGER NOT NULL DEFAULT 1,
    moneda        TEXT    NOT NULL DEFAULT 'COP', -- 'COP' | 'USD' | 'EUR' | 'GBP'
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Configuración clave-valor
CREATE TABLE configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
```

### Índices

```sql
CREATE INDEX idx_gastos_fecha     ON gastos(fecha);
CREATE INDEX idx_gastos_categoria ON gastos(categoria_id);
CREATE INDEX idx_gastos_tarjeta   ON gastos(tarjeta_id);
CREATE INDEX idx_gastos_periodo   ON gastos(corte_periodo);
```

### Migración automática

`db.py` ejecuta `_migrate()` en cada arranque: agrega columnas nuevas a bases de datos existentes de forma idempotente (usando `ALTER TABLE ... ADD COLUMN` con captura de excepciones).

### Backup manual

```python
from db import Database
db = Database()
db.backup('/ruta/destino/gastos_backup.db')
```

---

## Configuración

Las claves se almacenan en la tabla `configuracion`. Valores predeterminados:

| Clave | Predeterminado | Descripción |
|---|---|---|
| `nombre_usuario` | `Usuario` | Nombre que aparece en reportes PDF |
| `moneda` | `COP` | Moneda base de visualización |
| `presupuesto_mensual` | `3000000` | Presupuesto mensual (en moneda base) |
| `tema` | `dark` | Tema visual: `dark` o `light` |
| `tasa_usd_cop` | `4200` | Tasa de conversión USD → COP |
| `tasa_eur_cop` | `4600` | Tasa de conversión EUR → COP |
| `tasa_gbp_cop` | `5300` | Tasa de conversión GBP → COP |

Leer/escribir desde código:

```python
db.get_config('moneda', 'COP')   # → 'COP'
db.set_config('moneda', 'USD')
```

---

## Construir el ejecutable

Genera un `.exe` para Windows que no requiere Python instalado:

```bash
pip install pyinstaller

pyinstaller --clean --onedir --windowed --name GastosApp --collect-all customtkinter main.py
```

El ejecutable queda en `dist\GastosApp\GastosApp.exe`.  
Para distribuirlo, comparte **toda la carpeta** `dist\GastosApp\`.

| Flag | Descripción |
|---|---|
| `--onedir` | Carpeta con el exe y sus DLLs (más estable que `--onefile`) |
| `--windowed` | Sin ventana de consola negra |
| `--collect-all customtkinter` | Incluye temas e imágenes de CTk |

> La base de datos (`~/.gastos_app/gastos.db`) es independiente del ejecutable y se crea automáticamente en la primera ejecución.

---

## Guía de contribución

### Agregar una vista nueva

1. Crear `views/mi_vista.py` con una clase que herede de `ctk.CTkFrame`:

```python
class MiVista(ctk.CTkFrame):
    def __init__(self, parent, db: Database, navigate: Callable):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.navigate = navigate
        self._build()

    def _build(self):
        # construir widgets aquí
        pass

    def refresh(self, **kwargs):
        # llamado automáticamente al navegar a esta vista
        pass
```

2. Importar y registrar en `app.py`:

```python
from views.mi_vista import MiVista

# En _setup_views():
'mi_vista': lambda: MiVista(self.content, self.db, self.navigate),

# En NAV_ITEMS:
('mi_vista', '🆕  Mi Vista'),
```

### Agregar una columna a `gastos`

1. Agregar el `ALTER TABLE` en el método `_migrate()` de `db.py` (ya existe el patrón).
2. Actualizar `models.py` → dataclass `Gasto`.
3. Actualizar `_row_to_gasto()` en `db.py`.
4. Actualizar `add_gasto()` y `update_gasto()` con el nuevo campo.

### Convenciones de código

- **Formato:** PEP 8. Líneas ≤ 100 caracteres.
- **Tipos:** anotaciones en funciones públicas (`def foo(x: int) -> str`).
- **Widgets:** construir en `_build()`, actualizar datos en `refresh()`.
- **BD:** nunca ejecutar SQL fuera de `db.py`; agregar métodos a `Database`.
- **Commits:** mensajes en español, imperativo (`Agrega filtro por método`, `Corrige cálculo de corte`).

### Ramas sugeridas

```
main          → código estable
feature/xxx   → nuevas funcionalidades
fix/xxx       → correcciones de bugs
```
