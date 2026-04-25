import calendar
from datetime import date, datetime, timedelta
from typing import Tuple


# ─────────────────────────────────────────────
# Billing-cycle logic
# ─────────────────────────────────────────────

def calcular_corte_periodo(fecha_str: str, dia_corte: int) -> str:
    """
    Returns the billing-cycle period (YYYY-MM) for a given expense date and cut day.

    Rule:
      fecha.day < dia_corte  → expense belongs to current month's cut
      fecha.day >= dia_corte → expense belongs to next month's cut
    """
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    if fecha.day < dia_corte:
        return f"{fecha.year}-{fecha.month:02d}"
    else:
        if fecha.month == 12:
            return f"{fecha.year + 1}-01"
        return f"{fecha.year}-{fecha.month + 1:02d}"


def fecha_corte_desde_periodo(periodo: str, dia_corte: int) -> date:
    """Returns the actual calendar date when a billing period closes."""
    year, month = map(int, periodo.split('-'))
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(dia_corte, max_day))


def fecha_limite_pago(fecha_corte: date, dia_pago: int) -> date:
    """Returns the payment due date (dia_pago of the month following the cut)."""
    if fecha_corte.month == 12:
        year, month = fecha_corte.year + 1, 1
    else:
        year, month = fecha_corte.year, fecha_corte.month + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(dia_pago, max_day))


def periodo_actual(dia_corte: int) -> str:
    return calcular_corte_periodo(date.today().strftime('%Y-%m-%d'), dia_corte)


def proximo_periodo(dia_corte: int) -> str:
    current = periodo_actual(dia_corte)
    year, month = map(int, current.split('-'))
    if month == 12:
        return f"{year + 1}-01"
    return f"{year}-{month + 1:02d}"


def periodos_tarjeta(dia_corte: int, dia_pago: int) -> dict:
    """Returns a dict with all relevant dates for a credit card."""
    today = date.today()
    periodo_act = periodo_actual(dia_corte)
    periodo_prox = proximo_periodo(dia_corte)
    corte_act = fecha_corte_desde_periodo(periodo_act, dia_corte)
    corte_prox = fecha_corte_desde_periodo(periodo_prox, dia_corte)
    pago_act = fecha_limite_pago(corte_act, dia_pago)
    return {
        'periodo_actual': periodo_act,
        'periodo_proximo': periodo_prox,
        'fecha_corte_actual': corte_act,
        'fecha_corte_proximo': corte_prox,
        'fecha_limite_pago': pago_act,
        'dias_para_corte': (corte_act - today).days,
        'dias_para_pago': (pago_act - today).days,
    }


# ─────────────────────────────────────────────
# Date helpers
# ─────────────────────────────────────────────

def format_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return date_str


def format_date_long(date_str: str) -> str:
    MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
             'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{d.day} {MESES[d.month - 1]} {d.year}"
    except Exception:
        return date_str


def periodo_label(periodo: str) -> str:
    """'2025-04' → 'Abr 2025'"""
    MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
             'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    try:
        year, month = map(int, periodo.split('-'))
        return f"{MESES[month - 1]} {year}"
    except Exception:
        return periodo


def date_to_iso(d: date) -> str:
    return d.strftime('%Y-%m-%d')


def today_iso() -> str:
    return date.today().strftime('%Y-%m-%d')


def mes_anterior_periodo() -> Tuple[str, str]:
    """Returns (first_day, last_day) of last month as ISO strings."""
    today = date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return date_to_iso(first_prev), date_to_iso(last_prev)


def mes_actual_periodo() -> Tuple[str, str]:
    """Returns (first_day, last_day) of current month as ISO strings."""
    today = date.today()
    first = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    last = today.replace(day=last_day)
    return date_to_iso(first), date_to_iso(last)


def ultimos_n_meses(n: int) -> list:
    """Returns list of 'YYYY-MM' strings for the last n months (oldest first)."""
    today = date.today()
    result = []
    for i in range(n - 1, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        result.append(f"{year}-{month:02d}")
    return result


# ─────────────────────────────────────────────
# Currency / number formatting
# ─────────────────────────────────────────────

MONEDAS = ['COP', 'USD', 'EUR', 'GBP']

_SYM = {'COP': '$', 'USD': 'US$', 'EUR': '€', 'GBP': '£'}
_DECIMALS = {'COP': 0, 'USD': 2, 'EUR': 2, 'GBP': 2}


def format_currency(amount: float, currency: str = 'COP', short: bool = False) -> str:
    sym = _SYM.get(currency, f'{currency} $')
    dec = _DECIMALS.get(currency, 2)
    if short:
        if abs(amount) >= 1_000_000:
            return f"{sym}{amount / 1_000_000:.1f}M"
        if abs(amount) >= 1_000:
            return f"{sym}{amount / 1_000:.0f}K"
    if dec == 0:
        return f"{sym}{amount:,.0f}"
    return f"{sym}{amount:,.{dec}f}"


def convertir_a_cop(amount: float, moneda: str, tasas: dict) -> float:
    """Convert amount from moneda to COP using a tasas dict
    (keys like 'tasa_usd_cop', 'tasa_eur_cop', 'tasa_gbp_cop')."""
    if moneda == 'COP':
        return amount
    key = f'tasa_{moneda.lower()}_cop'
    try:
        tasa = float(tasas.get(key, 0) or 0)
    except (ValueError, TypeError):
        tasa = 0.0
    return amount * tasa if tasa > 0 else 0.0


def parse_amount(text: str) -> float:
    """Parse user-typed amount, removing currency symbols and commas."""
    clean = (text.replace('$', '').replace(',', '').replace(' ', '')
               .replace('COP', '').replace('US', '').replace('€', '')
               .replace('£', '').replace('US$', ''))
    return float(clean)


# ─────────────────────────────────────────────
# Color helpers
# ─────────────────────────────────────────────

PALETTE = [
    '#F44336', '#E91E63', '#9C27B0', '#673AB7',
    '#3F51B5', '#2196F3', '#03A9F4', '#00BCD4',
    '#009688', '#4CAF50', '#8BC34A', '#CDDC39',
    '#FFC107', '#FF9800', '#FF5722', '#795548',
    '#607D8B', '#9E9E9E',
]


def darken(hex_color: str, factor: float = 0.7) -> str:
    """Returns a darker version of a hex color."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"
