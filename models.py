from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Categoria:
    id: Optional[int]
    nombre: str
    color: str = '#2196F3'


@dataclass
class Tarjeta:
    id: Optional[int]
    nombre: str
    banco: str
    dia_corte: int
    dia_pago: int
    activa: bool = True


@dataclass
class Gasto:
    id: Optional[int]
    descripcion: str
    monto: float
    fecha: str          # ISO format YYYY-MM-DD
    categoria_id: Optional[int]
    metodo_pago: str    # 'Efectivo' | 'Tarjeta de crédito' | 'Débito/Transferencia'
    tarjeta_id: Optional[int] = None
    corte_periodo: Optional[str] = None  # 'YYYY-MM'
    notas: str = ''
    cuotas: int = 1          # number of installments (1 = contado)
    moneda: str = 'COP'      # currency: COP | USD | EUR | GBP
    created_at: Optional[str] = None
    # Joined fields (not stored)
    categoria_nombre: Optional[str] = None
    categoria_color: Optional[str] = None
    tarjeta_nombre: Optional[str] = None
