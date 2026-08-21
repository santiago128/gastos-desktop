import os
import sqlite3
import shutil
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from models import Gasto, Tarjeta, Categoria
from utils import calcular_corte_periodo, today_iso

DB_DIR = os.path.join(os.path.expanduser('~'), '.gastos_app')
DB_PATH = os.path.join(DB_DIR, 'gastos.db')


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn: sqlite3.Connection = None
        self._connect()
        self._create_tables()
        self._seed_if_empty()

    # ─────────────────────────────────────────
    # Connection
    # ─────────────────────────────────────────

    def _connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")

    def close(self):
        if self.conn:
            self.conn.close()

    # ─────────────────────────────────────────
    # Schema
    # ─────────────────────────────────────────

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS deudas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                deudor       TEXT    NOT NULL,
                descripcion  TEXT    NOT NULL,
                monto        REAL    NOT NULL,
                monto_pagado REAL    NOT NULL DEFAULT 0,
                fecha        TEXT    NOT NULL,
                fecha_pago   TEXT,
                notas        TEXT    NOT NULL DEFAULT '',
                moneda       TEXT    NOT NULL DEFAULT 'COP',
                estado       TEXT    NOT NULL DEFAULT 'pendiente',
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS categorias (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT    NOT NULL UNIQUE,
                color  TEXT    NOT NULL DEFAULT '#2196F3'
            );

            CREATE TABLE IF NOT EXISTS tarjetas (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre    TEXT    NOT NULL,
                banco     TEXT    NOT NULL DEFAULT '',
                dia_corte INTEGER NOT NULL,
                dia_pago  INTEGER NOT NULL,
                activa    INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS gastos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion   TEXT    NOT NULL,
                monto         REAL    NOT NULL,
                fecha         TEXT    NOT NULL,
                categoria_id  INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                metodo_pago   TEXT    NOT NULL,
                tarjeta_id    INTEGER REFERENCES tarjetas(id)   ON DELETE SET NULL,
                corte_periodo TEXT,
                notas         TEXT    NOT NULL DEFAULT '',
                cuotas        INTEGER NOT NULL DEFAULT 1,
                moneda        TEXT    NOT NULL DEFAULT 'COP',
                created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL DEFAULT ''
            );
        """)
        self._migrate()
        # Indexes for fast date-range and join queries
        self.conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_gastos_fecha     ON gastos(fecha);
            CREATE INDEX IF NOT EXISTS idx_gastos_categoria ON gastos(categoria_id);
            CREATE INDEX IF NOT EXISTS idx_gastos_tarjeta   ON gastos(tarjeta_id);
            CREATE INDEX IF NOT EXISTS idx_gastos_periodo   ON gastos(corte_periodo);
        """)
        self.conn.commit()

    def _migrate(self):
        """Safe column additions for existing databases (idempotent)."""
        for sql in [
            "ALTER TABLE gastos ADD COLUMN cuotas INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE gastos ADD COLUMN moneda TEXT NOT NULL DEFAULT 'COP'",
        ]:
            try:
                self.conn.execute(sql)
            except Exception:
                pass

    # ─────────────────────────────────────────
    # Seed
    # ─────────────────────────────────────────

    def _seed_if_empty(self):
        if self.conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] > 0:
            return

        # Default config
        defaults = [
            ('nombre_usuario', 'Usuario'),
            ('moneda', 'COP'),
            ('presupuesto_mensual', '3000000'),
            ('tema', 'dark'),
            ('tasa_usd_cop', '4200'),
            ('tasa_eur_cop', '4600'),
            ('tasa_gbp_cop', '5300'),
        ]
        self.conn.executemany(
            "INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", defaults
        )

        # Categories
        cats_data = [
            ('Alimentación',    '#F44336'),
            ('Transporte',      '#FF9800'),
            ('Entretenimiento', '#9C27B0'),
            ('Salud',           '#4CAF50'),
            ('Servicios',       '#2196F3'),
            ('Ropa',            '#E91E63'),
            ('Educación',       '#3F51B5'),
            ('Vivienda',        '#795548'),
            ('Tecnología',      '#00BCD4'),
            ('Restaurantes',    '#FF5722'),
            ('Supermercado',    '#8BC34A'),
            ('Viajes',          '#009688'),
            ('Otros',           '#607D8B'),
        ]
        self.conn.executemany("INSERT INTO categorias (nombre, color) VALUES (?, ?)", cats_data)

        # Credit cards
        tarjetas_data = [
            ('Visa Bancolombia',      'Bancolombia', 15, 5),
            ('Mastercard Davivienda', 'Davivienda',  20, 10),
            ('Amex Falabella',        'Falabella',   25, 15),
        ]
        self.conn.executemany(
            "INSERT INTO tarjetas (nombre, banco, dia_corte, dia_pago) VALUES (?, ?, ?, ?)",
            tarjetas_data,
        )
        self.conn.commit()

        cats  = {r['nombre']: r['id'] for r in self.conn.execute("SELECT id, nombre FROM categorias")}
        tarjs = [r['id'] for r in self.conn.execute("SELECT id FROM tarjetas ORDER BY id")]
        t1, t2, t3 = tarjs[0], tarjs[1], tarjs[2]

        dc = {t1: 15, t2: 20, t3: 25}   # dia_corte per card

        today = date.today()

        def _d(days_ago: int) -> str:
            return (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')

        def cc(desc, monto, days_ago, cat, tid, notas='', cuotas=1, moneda='COP'):
            f = _d(days_ago)
            return (desc, monto, f, cats.get(cat, 1), 'Tarjeta de crédito', tid,
                    calcular_corte_periodo(f, dc[tid]), notas, cuotas, moneda)

        def ef(desc, monto, days_ago, cat, notas='', moneda='COP'):
            return (desc, monto, _d(days_ago), cats.get(cat, 1), 'Efectivo',
                    None, None, notas, 1, moneda)

        def deb(desc, monto, days_ago, cat, notas='', moneda='COP'):
            return (desc, monto, _d(days_ago), cats.get(cat, 1),
                    'Débito/Transferencia', None, None, notas, 1, moneda)

        gastos_sample = [
            # Este mes
            cc('Netflix',                    45_900, 2,  'Entretenimiento', t1),
            cc('Éxito — Mercado mensual',   385_000, 5,  'Supermercado',    t1),
            cc('Cruz Verde — Medicamentos',  78_500, 3,  'Salud',           t2),
            cc('Zara — Camisa',             129_000, 8,  'Ropa',            t2, cuotas=6),
            cc('Apple One',                  52_000, 1,  'Tecnología',      t3),
            cc('Amazon — Libro Python',      62_000, 12, 'Educación',       t1),
            cc('Curso Udemy',                   19, 6,   'Educación',       t1, moneda='USD'),
            cc('Adobe Creative Cloud',          55, 4,   'Tecnología',      t2, moneda='USD'),
            ef('Taxi Urbano',                15_000, 4,  'Transporte'),
            ef('Almuerzo Ejecutivo',         18_500, 6,  'Restaurantes'),
            ef('Desayuno cafetería',         12_000, 2,  'Alimentación'),
            ef('Bus TransMilenio',            5_400, 9,  'Transporte'),
            deb('Recibo de Luz EPM',         95_000, 7,  'Servicios'),
            deb('Internet Claro',            75_000, 10, 'Servicios'),
            deb('Gimnasio mensualidad',     120_000, 1,  'Salud'),
            # Mes pasado
            cc('Cinema — Cinépolis',         32_000, 35, 'Entretenimiento', t1),
            cc('Éxito — Mercado',           320_000, 40, 'Supermercado',    t2),
            cc('Rappi — Domicilio pizza',    48_000, 33, 'Restaurantes',    t1),
            cc('Renta vehículo fin semana', 250_000, 45, 'Transporte',      t3, cuotas=3),
            cc('JUMBO — Artículos hogar',   185_000, 50, 'Vivienda',        t2,
               notas='Cortinas y almohadas', cuotas=12),
            ef('Mercado campesino',          95_000, 38, 'Alimentación'),
            ef('Barbería',                   30_000, 42, 'Otros'),
            deb('Gas Natural',              45_000,  37, 'Servicios'),
            deb('Spotify Premium',          17_900,  32, 'Entretenimiento'),
            ef('Farmacia — Medicamentos',   67_000,  48, 'Salud'),
            cc('Vuelo Bogotá-Cali',        320_000,  55, 'Viajes',  t3,
               notas='Puente festivo', cuotas=2),
        ]

        self.conn.executemany(
            """INSERT INTO gastos
               (descripcion, monto, fecha, categoria_id, metodo_pago,
                tarjeta_id, corte_periodo, notas, cuotas, moneda)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            gastos_sample,
        )
        self.conn.commit()

    # ─────────────────────────────────────────
    # Configuración
    # ─────────────────────────────────────────

    def get_config(self, clave: str, default: str = '') -> str:
        row = self.conn.execute(
            "SELECT valor FROM configuracion WHERE clave = ?", (clave,)
        ).fetchone()
        return row['valor'] if row else default

    def set_config(self, clave: str, valor: str):
        self.conn.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor),
        )
        self.conn.commit()

    def get_all_config(self) -> dict:
        rows = self.conn.execute("SELECT clave, valor FROM configuracion").fetchall()
        return {r['clave']: r['valor'] for r in rows}

    # ─────────────────────────────────────────
    # Categorías
    # ─────────────────────────────────────────

    def get_categorias(self) -> List[Categoria]:
        rows = self.conn.execute(
            "SELECT id, nombre, color FROM categorias ORDER BY nombre"
        ).fetchall()
        return [Categoria(r['id'], r['nombre'], r['color']) for r in rows]

    def add_categoria(self, nombre: str, color: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO categorias (nombre, color) VALUES (?, ?)", (nombre, color)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_categoria(self, cat_id: int, nombre: str, color: str):
        self.conn.execute(
            "UPDATE categorias SET nombre = ?, color = ? WHERE id = ?",
            (nombre, color, cat_id),
        )
        self.conn.commit()

    def delete_categoria(self, cat_id: int, reassign_to: Optional[int] = None):
        if reassign_to is not None:
            self.conn.execute(
                "UPDATE gastos SET categoria_id = ? WHERE categoria_id = ?",
                (reassign_to, cat_id),
            )
        else:
            self.conn.execute(
                "UPDATE gastos SET categoria_id = NULL WHERE categoria_id = ?", (cat_id,)
            )
        self.conn.execute("DELETE FROM categorias WHERE id = ?", (cat_id,))
        self.conn.commit()

    def categoria_expense_count(self, cat_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM gastos WHERE categoria_id = ?", (cat_id,)
        ).fetchone()[0]

    # ─────────────────────────────────────────
    # Tarjetas
    # ─────────────────────────────────────────

    def get_tarjetas(self, solo_activas: bool = False) -> List[Tarjeta]:
        sql = "SELECT * FROM tarjetas"
        if solo_activas:
            sql += " WHERE activa = 1"
        sql += " ORDER BY nombre"
        rows = self.conn.execute(sql).fetchall()
        return [Tarjeta(r['id'], r['nombre'], r['banco'],
                        r['dia_corte'], r['dia_pago'], bool(r['activa']))
                for r in rows]

    def get_tarjeta(self, tarjeta_id: int) -> Optional[Tarjeta]:
        row = self.conn.execute(
            "SELECT * FROM tarjetas WHERE id = ?", (tarjeta_id,)
        ).fetchone()
        if not row:
            return None
        return Tarjeta(row['id'], row['nombre'], row['banco'],
                       row['dia_corte'], row['dia_pago'], bool(row['activa']))

    def add_tarjeta(self, t: Tarjeta) -> int:
        cur = self.conn.execute(
            "INSERT INTO tarjetas (nombre, banco, dia_corte, dia_pago, activa) "
            "VALUES (?, ?, ?, ?, ?)",
            (t.nombre, t.banco, t.dia_corte, t.dia_pago, int(t.activa)),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_tarjeta(self, t: Tarjeta):
        self.conn.execute(
            "UPDATE tarjetas SET nombre=?, banco=?, dia_corte=?, dia_pago=?, activa=? "
            "WHERE id=?",
            (t.nombre, t.banco, t.dia_corte, t.dia_pago, int(t.activa), t.id),
        )
        self.conn.commit()

    def delete_tarjeta(self, tarjeta_id: int):
        self.conn.execute(
            "UPDATE gastos SET tarjeta_id = NULL, metodo_pago = 'Débito/Transferencia' "
            "WHERE tarjeta_id = ?", (tarjeta_id,)
        )
        self.conn.execute("DELETE FROM tarjetas WHERE id = ?", (tarjeta_id,))
        self.conn.commit()

    def get_total_tarjeta_periodo(self, tarjeta_id: int, periodo: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM gastos "
            "WHERE tarjeta_id = ? AND corte_periodo = ?",
            (tarjeta_id, periodo),
        ).fetchone()
        return row[0]

    def get_gastos_tarjeta_periodo(self, tarjeta_id: int, periodo: str) -> List[Gasto]:
        rows = self.conn.execute(
            """SELECT g.*, c.nombre AS cat_nombre, c.color AS cat_color
               FROM gastos g
               LEFT JOIN categorias c ON g.categoria_id = c.id
               WHERE g.tarjeta_id = ? AND g.corte_periodo = ?
               ORDER BY g.fecha DESC""",
            (tarjeta_id, periodo),
        ).fetchall()
        return [self._row_to_gasto(r) for r in rows]

    # ─────────────────────────────────────────
    # Gastos
    # ─────────────────────────────────────────

    def add_gasto(self, g: Gasto) -> int:
        cur = self.conn.execute(
            """INSERT INTO gastos
               (descripcion, monto, fecha, categoria_id, metodo_pago,
                tarjeta_id, corte_periodo, notas, cuotas, moneda)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (g.descripcion, g.monto, g.fecha, g.categoria_id,
             g.metodo_pago, g.tarjeta_id, g.corte_periodo, g.notas,
             g.cuotas, g.moneda),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_gasto(self, g: Gasto):
        self.conn.execute(
            """UPDATE gastos SET
               descripcion=?, monto=?, fecha=?, categoria_id=?,
               metodo_pago=?, tarjeta_id=?, corte_periodo=?, notas=?,
               cuotas=?, moneda=?
               WHERE id=?""",
            (g.descripcion, g.monto, g.fecha, g.categoria_id,
             g.metodo_pago, g.tarjeta_id, g.corte_periodo, g.notas,
             g.cuotas, g.moneda, g.id),
        )
        self.conn.commit()

    def delete_gasto(self, gasto_id: int):
        self.conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
        self.conn.commit()

    def get_gasto(self, gasto_id: int) -> Optional[Gasto]:
        row = self.conn.execute(
            """SELECT g.*, c.nombre AS cat_nombre, c.color AS cat_color,
                      t.nombre AS tarjeta_nombre
               FROM gastos g
               LEFT JOIN categorias c ON g.categoria_id = c.id
               LEFT JOIN tarjetas   t ON g.tarjeta_id   = t.id
               WHERE g.id = ?""",
            (gasto_id,),
        ).fetchone()
        return self._row_to_gasto(row) if row else None

    def get_gastos(
        self,
        fecha_desde: str = None,
        fecha_hasta: str = None,
        categoria_id: int = None,
        metodo_pago: str = None,
        tarjeta_id: int = None,
        busqueda: str = None,
        limit: int = None,
        offset: int = 0,
    ) -> List[Gasto]:
        sql = """
            SELECT g.*, c.nombre AS cat_nombre, c.color AS cat_color,
                   t.nombre AS tarjeta_nombre
            FROM gastos g
            LEFT JOIN categorias c ON g.categoria_id = c.id
            LEFT JOIN tarjetas   t ON g.tarjeta_id   = t.id
            WHERE 1=1
        """
        params: list = []

        if fecha_desde:
            sql += " AND g.fecha >= ?"
            params.append(fecha_desde)
        if fecha_hasta:
            sql += " AND g.fecha <= ?"
            params.append(fecha_hasta)
        if categoria_id is not None:
            sql += " AND g.categoria_id = ?"
            params.append(categoria_id)
        if metodo_pago:
            sql += " AND g.metodo_pago = ?"
            params.append(metodo_pago)
        if tarjeta_id is not None:
            sql += " AND g.tarjeta_id = ?"
            params.append(tarjeta_id)
        if busqueda:
            sql += " AND g.descripcion LIKE ?"
            params.append(f"%{busqueda}%")

        sql += " ORDER BY g.fecha DESC, g.id DESC"

        if limit:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_gasto(r) for r in rows]

    @staticmethod
    def _row_to_gasto(row) -> Gasto:
        g = Gasto(
            id=row['id'],
            descripcion=row['descripcion'],
            monto=row['monto'],
            fecha=row['fecha'],
            categoria_id=row['categoria_id'],
            metodo_pago=row['metodo_pago'],
            tarjeta_id=row['tarjeta_id'],
            corte_periodo=row['corte_periodo'],
            notas=row['notas'] or '',
            created_at=row['created_at'],
        )
        try:
            g.cuotas = int(row['cuotas'] or 1)
        except Exception:
            g.cuotas = 1
        try:
            g.moneda = row['moneda'] or 'COP'
        except Exception:
            g.moneda = 'COP'
        try:
            g.categoria_nombre = row['cat_nombre']
            g.categoria_color  = row['cat_color']
        except Exception:
            pass
        try:
            g.tarjeta_nombre = row['tarjeta_nombre']
        except Exception:
            pass
        return g

    # ─────────────────────────────────────────
    # Statistics
    # ─────────────────────────────────────────

    def get_total_mes(self, year: int, month: int) -> float:
        """Total spending for YYYY-MM.
        Cash/debit: by calendar date. TC: by corte_periodo so post-cutoff
        purchases are counted in the month they will actually be charged."""
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        fecha_desde = f"{year}-{month:02d}-01"
        fecha_hasta = f"{year}-{month:02d}-{last:02d}"
        periodo = f"{year}-{month:02d}"
        row = self.conn.execute(
            """SELECT COALESCE(SUM(monto), 0) FROM gastos
               WHERE (metodo_pago != 'Tarjeta de crédito'
                      AND fecha >= ? AND fecha <= ?)
                  OR (metodo_pago  = 'Tarjeta de crédito'
                      AND corte_periodo = ?)""",
            (fecha_desde, fecha_hasta, periodo),
        ).fetchone()
        return row[0]

    def get_totales_por_mes(self, n_meses: int = 6) -> List[Dict]:
        """Returns list of {periodo, total} for the last n months."""
        from utils import ultimos_n_meses
        import calendar as _cal
        periodos = ultimos_n_meses(n_meses)
        result = []
        for p in periodos:
            y, m = map(int, p.split('-'))
            total = self.get_total_mes(y, m)
            result.append({'periodo': p, 'total': total})
        return result

    def get_totales_por_categoria_mes(self, year: int, month: int) -> List[Dict]:
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        rows = self.conn.execute(
            """SELECT c.nombre, c.color, COALESCE(SUM(g.monto), 0) AS total
               FROM categorias c
               LEFT JOIN gastos g
                 ON g.categoria_id = c.id
                 AND g.fecha >= ? AND g.fecha <= ?
               GROUP BY c.id
               HAVING total > 0
               ORDER BY total DESC""",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"),
        ).fetchall()
        return [{'nombre': r['nombre'], 'color': r['color'], 'total': r['total']} for r in rows]

    def get_totales_por_categoria_periodo(self, fecha_desde: str, fecha_hasta: str) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT c.nombre, c.color, COALESCE(SUM(g.monto), 0) AS total
               FROM categorias c
               LEFT JOIN gastos g
                 ON g.categoria_id = c.id
                 AND g.fecha >= ? AND g.fecha <= ?
               GROUP BY c.id
               HAVING total > 0
               ORDER BY total DESC""",
            (fecha_desde, fecha_hasta),
        ).fetchall()
        return [{'nombre': r['nombre'], 'color': r['color'], 'total': r['total']} for r in rows]

    def get_gastos_recientes(self, limit: int = 10) -> List[Gasto]:
        return self.get_gastos(limit=limit)

    def get_total_pagado_mes(self, year: int, month: int) -> dict:
        """
        TC billing summary for YYYY-MM, respecting installment cycles.

        - total_compras:  monto of purchases whose corte_periodo = YYYY-MM
                          (new purchases entering the billing cycle this month)
        - total_cuotas:   sum of active installment payments this month,
                          including ongoing cuotas from previous cycles
        - n_gastos:       purchases with corte_periodo = YYYY-MM
        - n_en_cuotas:    of those, count with cuotas > 1
        - avg_cuotas:     average installment count (among multi-cuota)
        """
        periodo_target = f"{year}-{month:02d}"

        # New purchases entering the cycle this month
        new_rows = self.conn.execute(
            """SELECT monto, cuotas FROM gastos
               WHERE corte_periodo = ?
               AND metodo_pago = 'Tarjeta de crédito'""",
            (periodo_target,),
        ).fetchall()
        total_compras = sum(r['monto'] for r in new_rows)
        n_en_cuotas   = sum(1 for r in new_rows if (r['cuotas'] or 1) > 1)
        avg_c = (sum(int(r['cuotas']) for r in new_rows if (r['cuotas'] or 1) > 1)
                 / n_en_cuotas) if n_en_cuotas else 0

        # All TC purchases whose installments are still active in this month:
        # corte_periodo <= target AND corte_periodo + (cuotas-1) months >= target
        all_rows = self.conn.execute(
            """SELECT monto, cuotas, corte_periodo FROM gastos
               WHERE corte_periodo <= ?
               AND corte_periodo IS NOT NULL
               AND metodo_pago = 'Tarjeta de crédito'""",
            (periodo_target,),
        ).fetchall()

        total_cuotas = 0.0
        for r in all_rows:
            cuotas = max(int(r['cuotas'] or 1), 1)
            p_year, p_month = map(int, r['corte_periodo'].split('-'))
            # Last installment month = corte_periodo + (cuotas - 1) months
            lm = p_month + cuotas - 1
            last_periodo = f"{p_year + (lm - 1) // 12}-{(lm - 1) % 12 + 1:02d}"
            if last_periodo >= periodo_target:
                total_cuotas += r['monto'] / cuotas

        return {
            'total_compras': total_compras,
            'total_cuotas':  total_cuotas,
            'n_gastos':      len(new_rows),
            'n_en_cuotas':   n_en_cuotas,
            'avg_cuotas':    avg_c,
        }

    def get_totales_por_moneda_mes(self, year: int, month: int) -> List[Dict]:
        """Returns [{moneda, total}] for all currencies used in the month."""
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        rows = self.conn.execute(
            """SELECT moneda, SUM(monto) AS total
               FROM gastos
               WHERE fecha >= ? AND fecha <= ?
               GROUP BY moneda HAVING total > 0
               ORDER BY total DESC""",
            (f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"),
        ).fetchall()
        return [{'moneda': r['moneda'] or 'COP', 'total': r['total']} for r in rows]

    # ─────────────────────────────────────────
    # Deudas (dinero que me deben)
    # ─────────────────────────────────────────

    def get_deudas(self, estado: str = None) -> list:
        sql = "SELECT * FROM deudas"
        params = []
        if estado:
            sql += " WHERE estado = ?"
            params.append(estado)
        sql += " ORDER BY estado ASC, fecha DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def add_deuda(self, deudor: str, descripcion: str, monto: float,
                  fecha: str, notas: str = '', moneda: str = 'COP') -> int:
        cur = self.conn.execute(
            """INSERT INTO deudas (deudor, descripcion, monto, fecha, notas, moneda)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (deudor, descripcion, monto, fecha, notas, moneda),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_deuda(self, deuda_id: int, deudor: str, descripcion: str,
                     monto: float, fecha: str, notas: str, moneda: str):
        self.conn.execute(
            """UPDATE deudas SET deudor=?, descripcion=?, monto=?, fecha=?,
               notas=?, moneda=? WHERE id=?""",
            (deudor, descripcion, monto, fecha, notas, moneda, deuda_id),
        )
        self._recalc_estado(deuda_id)
        self.conn.commit()

    def registrar_pago_deuda(self, deuda_id: int, monto_pago: float,
                              fecha_pago: str = None):
        """Suma monto_pago al monto_pagado y actualiza estado."""
        from utils import today_iso
        row = self.conn.execute(
            "SELECT monto, monto_pagado FROM deudas WHERE id=?", (deuda_id,)
        ).fetchone()
        if not row:
            return
        nuevo_pagado = min(row['monto_pagado'] + monto_pago, row['monto'])
        fp = fecha_pago or today_iso()
        if nuevo_pagado >= row['monto']:
            estado = 'pagado'
        elif nuevo_pagado > 0:
            estado = 'parcial'
        else:
            estado = 'pendiente'
        self.conn.execute(
            """UPDATE deudas SET monto_pagado=?, estado=?, fecha_pago=?
               WHERE id=?""",
            (nuevo_pagado, estado, fp if estado == 'pagado' else None, deuda_id),
        )
        self.conn.commit()

    def delete_deuda(self, deuda_id: int):
        self.conn.execute("DELETE FROM deudas WHERE id=?", (deuda_id,))
        self.conn.commit()

    def _recalc_estado(self, deuda_id: int):
        row = self.conn.execute(
            "SELECT monto, monto_pagado FROM deudas WHERE id=?", (deuda_id,)
        ).fetchone()
        if not row:
            return
        mp = row['monto_pagado']
        if mp >= row['monto']:
            estado = 'pagado'
        elif mp > 0:
            estado = 'parcial'
        else:
            estado = 'pendiente'
        self.conn.execute("UPDATE deudas SET estado=? WHERE id=?", (estado, deuda_id))

    def get_resumen_deudas(self) -> dict:
        rows = self.conn.execute(
            "SELECT estado, SUM(monto) AS tm, SUM(monto_pagado) AS tp FROM deudas GROUP BY estado"
        ).fetchall()
        total_monto = total_pagado = 0.0
        by_estado = {}
        for r in rows:
            by_estado[r['estado']] = {'monto': r['tm'], 'pagado': r['tp']}
            total_monto  += r['tm']
            total_pagado += r['tp']
        return {
            'total_monto':    total_monto,
            'total_pagado':   total_pagado,
            'total_pendiente': total_monto - total_pagado,
            'by_estado':      by_estado,
        }

    # ─────────────────────────────────────────
    # Backup / export
    # ─────────────────────────────────────────

    def backup(self, dest_path: str):
        self.conn.commit()
        shutil.copy2(self.db_path, dest_path)
