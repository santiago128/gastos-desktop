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
                created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL DEFAULT ''
            );
        """)
        self.conn.commit()

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

        def cc(desc, monto, days_ago, cat, tid, notas=''):
            f = _d(days_ago)
            return (desc, monto, f, cats.get(cat, 1), 'Tarjeta de crédito', tid,
                    calcular_corte_periodo(f, dc[tid]), notas)

        def ef(desc, monto, days_ago, cat, notas=''):
            return (desc, monto, _d(days_ago), cats.get(cat, 1), 'Efectivo', None, None, notas)

        def deb(desc, monto, days_ago, cat, notas=''):
            return (desc, monto, _d(days_ago), cats.get(cat, 1), 'Débito/Transferencia', None, None, notas)

        gastos_sample = [
            # Este mes
            cc('Netflix',                    45_900, 2,  'Entretenimiento', t1),
            cc('Éxito — Mercado mensual',   385_000, 5,  'Supermercado',    t1),
            cc('Cruz Verde — Medicamentos',  78_500, 3,  'Salud',           t2),
            cc('Zara — Camisa',             129_000, 8,  'Ropa',            t2),
            cc('Apple One',                  52_000, 1,  'Tecnología',      t3),
            cc('Amazon — Libro Python',      62_000, 12, 'Educación',       t1),
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
            cc('Renta vehículo fin semana', 250_000, 45, 'Transporte',      t3),
            cc('JUMBO — Artículos hogar',   185_000, 50, 'Vivienda',        t2, 'Cortinas y almohadas'),
            ef('Mercado campesino',          95_000, 38, 'Alimentación'),
            ef('Barbería',                   30_000, 42, 'Otros'),
            deb('Gas Natural',              45_000,  37, 'Servicios'),
            deb('Spotify Premium',          17_900,  32, 'Entretenimiento'),
            ef('Farmacia — Medicamentos',   67_000,  48, 'Salud'),
            cc('Vuelo Bogotá-Cali',        320_000,  55, 'Viajes',          t3, 'Puente festivo'),
        ]

        self.conn.executemany(
            """INSERT INTO gastos
               (descripcion, monto, fecha, categoria_id, metodo_pago, tarjeta_id, corte_periodo, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
               (descripcion, monto, fecha, categoria_id, metodo_pago, tarjeta_id, corte_periodo, notas)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (g.descripcion, g.monto, g.fecha, g.categoria_id,
             g.metodo_pago, g.tarjeta_id, g.corte_periodo, g.notas),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_gasto(self, g: Gasto):
        self.conn.execute(
            """UPDATE gastos SET
               descripcion=?, monto=?, fecha=?, categoria_id=?,
               metodo_pago=?, tarjeta_id=?, corte_periodo=?, notas=?
               WHERE id=?""",
            (g.descripcion, g.monto, g.fecha, g.categoria_id,
             g.metodo_pago, g.tarjeta_id, g.corte_periodo, g.notas, g.id),
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
            g.categoria_nombre = row['cat_nombre']
            g.categoria_color = row['cat_color']
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
        fecha_desde = f"{year}-{month:02d}-01"
        import calendar as _cal
        last = _cal.monthrange(year, month)[1]
        fecha_hasta = f"{year}-{month:02d}-{last:02d}"
        row = self.conn.execute(
            "SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE fecha >= ? AND fecha <= ?",
            (fecha_desde, fecha_hasta),
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

    # ─────────────────────────────────────────
    # Backup / export
    # ─────────────────────────────────────────

    def backup(self, dest_path: str):
        self.conn.commit()
        shutil.copy2(self.db_path, dest_path)
