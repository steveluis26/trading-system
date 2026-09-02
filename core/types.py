"""Tipos canonicos. Research y produccion usan EXACTAMENTE estos.
Si el backtest y el live usan estructuras distintas, el sistema que validaste
no es el que opera. Esta es la causa #1 de fallo en vivo."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

class Side(str, Enum):
    BUY = "buy"; SELL = "sell"

class Timeframe(str, Enum):
    M1="M1"; M5="M5"; M15="M15"; M30="M30"; H1="H1"; H4="H4"; D1="D1"

@dataclass(frozen=True, slots=True)
class Bar:
    """Vela cerrada. bid/ask separados: el spread NO se asume constante."""
    time: datetime; open: float; high: float; low: float; close: float
    volume: float = 0.0
    spread: float = 0.0          # en puntos del instrumento
    symbol: str = ""
    timeframe: Timeframe = Timeframe.H1

@dataclass(frozen=True, slots=True)
class Signal:
    """Evento candidato producido por una estrategia. NO es una orden todavia:
    debe pasar por el Risk Engine. El ML se aplica sobre esto (meta-labeling)."""
    time: datetime; symbol: str; side: Side
    entry: float
    sl: float
    tp: float
    strategy: str
    confidence: float | None = None      # lo llena el modelo ML en Fase 3
    context: dict = field(default_factory=dict)   # features/razon, para trazabilidad
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def risk_reward(self) -> float:
        risk = abs(self.entry - self.sl)
        return abs(self.tp - self.entry) / risk if risk else 0.0

@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool; reason: str
    volume: float = 0.0
    correlation_id: str = ""

@dataclass(slots=True)
class Position:
    signal: Signal; volume: float
    open_time: datetime; open_price: float
    close_time: datetime | None = None
    close_price: float | None = None
    close_reason: str = ""
    commission: float = 0.0
    swap: float = 0.0
    breakeven_done: bool = False
    partial_pnl: float | None = None
    sl: float | None = None  # SL efectivo (mutable para breakeven); None = usa signal.sl

    @property
    def is_open(self) -> bool: return self.close_time is None

    def pnl(self, usd_per_pip: float = 10.0, pip_size: float = 0.0001) -> float:
        """P&L NETO. Sin costos, cualquier backtest miente.
        usd_per_pip = USD por pip por lote (oro=1, forex=10).
        pip_size usado solo para expresar la diferencia en pips."""
        if self.close_price is None: return 0.0
        diff_pips = (self.close_price - self.open_price) / pip_size
        if self.signal.side is Side.SELL: diff_pips = -diff_pips
        return diff_pips * self.volume * usd_per_pip + self.commission + self.swap
