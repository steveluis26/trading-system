"""
Data Models - Estructuras de datos tipadas para todo el backtester
Pydantic models para: Signal, Position, Trade, AccountState, SessionLevels, etc.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import pandas as pd


# ============================================================
# Enums
# ============================================================
class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"
    NEUTRAL = "NEUTRAL"


class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT_SL = "EXIT_SL"
    EXIT_TP = "EXIT_TP"
    EXIT_BREAKEVEN = "EXIT_BREAKEVEN"
    EXIT_PARTIAL = "EXIT_PARTIAL"
    EXIT_MANUAL = "EXIT_MANUAL"
    EXIT_FRIDAY_CLOSE = "EXIT_FRIDAY_CLOSE"
    BLOCKED_RISK = "BLOCKED_RISK"


class SessionName(str, Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEWYORK = "NEWYORK"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


# ============================================================
# Core Data Structures
# ============================================================
class SessionLevel(BaseModel):
    """High/Low de una sesión individual."""
    session: SessionName
    high: Optional[float] = None
    low: Optional[float] = None
    start_time: datetime
    end_time: datetime
    candle_count: int = 0


class SessionLevels(BaseModel):
    """Todos los niveles de sesión para un día."""
    date: datetime
    asia: SessionLevel
    london: SessionLevel
    newyork: SessionLevel
    timezone: str = "America/Mexico_City"
    
    def get_all_levels(self) -> List[tuple[SessionName, str, float]]:
        """Retorna [(session, 'HIGH'|'LOW', price), ...] para confluencia."""
        levels = []
        for sess_name, sess in [("ASIA", self.asia), ("LONDON", self.london), ("NEWYORK", self.newyork)]:
            if sess.high is not None:
                levels.append((SessionName(sess_name), "HIGH", sess.high))
            if sess.low is not None:
                levels.append((SessionName(sess_name), "LOW", sess.low))
        return levels


class ConfluenceZone(BaseModel):
    """Zona donde 2-3 sesiones coinciden en precio."""
    price: float
    sessions: List[SessionName]
    types: List[Literal["HIGH", "LOW"]]
    strength: int  # 2 o 3 sesiones
    is_high: bool
    is_low: bool
    tolerance_pips: float


class MarketStructure(BaseModel):
    """Análisis de estructura macro (1D/4H/1H)."""
    trend: Trend
    last_bos: Optional[Dict] = None
    pivots: List[Dict] = Field(default_factory=list)
    key_level: Optional[float] = None
    timeframe: str
    timestamp: datetime


class SweepEvent(BaseModel):
    """Evento de barrido detectado en 5M."""
    sweep_candle: Dict  # vela que perfora el nivel
    reclaim_candle: Dict  # vela que regresa y cierra del lado correcto
    sweep_index: int
    reclaim_index: int
    level: float
    direction: Direction
    penetration_pips: float
    wick_ratio: float
    candles_to_reclaim: int
    volume_spike: bool
    atr_value: float
    validation_passed: bool = False
    validation_reason: str = ""


class TradingSignal(BaseModel):
    """Señal generada por la estrategia (cerebro)."""
    signal_type: SignalType
    direction: Direction
    symbol: str
    entry_price: float
    sl_pips: float
    tp_pips: float
    sl_price: float
    tp_price: float
    lot_size: float
    confidence: float  # 0-1, peso de confluencia etc.
    timestamp: datetime
    trigger_level: float
    sweep_event: Optional[SweepEvent] = None
    session_levels: Optional[SessionLevels] = None
    market_structure: Optional[MarketStructure] = None
    validation_details: Dict = Field(default_factory=dict)
    
    # Para risk engine
    risk_pct: float = 0.01
    risk_amount_usd: float = 0.0


class RiskVerdict(BaseModel):
    """Resultado del risk engine (filtro)."""
    allow: bool
    reason: str
    risk_metrics: Dict = Field(default_factory=dict)


class Position(BaseModel):
    """Posición abierta en simulación/ejecución."""
    id: str
    signal: TradingSignal
    entry_time: datetime
    entry_price: float
    current_sl: float
    current_tp: float
    lot_size: float
    direction: Direction
    symbol: str
    status: Literal["OPEN", "CLOSED", "PARTIAL"] = "OPEN"
    breakeven_triggered: bool = False
    partials_executed: List[Dict] = Field(default_factory=list)
    max_favorable_pips: float = 0.0
    max_adverse_pips: float = 0.0
    
    def unrealized_pnl(self, current_price: float) -> float:
        """P&L no realizado en USD."""
        pip_value = self.signal.risk_amount_usd / (self.sl_pips * self.lot_size) if self.sl_pips > 0 else 0
        if self.direction == Direction.LONG:
            pips = (current_price - self.entry_price) / self.signal.symbol_pip_size
        else:
            pips = (self.entry_price - current_price) / self.signal.symbol_pip_size
        return pips * pip_value * self.lot_size


class ClosedTrade(BaseModel):
    """Operación cerrada con resultado completo."""
    position: Position
    exit_time: datetime
    exit_price: float
    exit_reason: SignalType
    pnl_usd: float
    pnl_pips: float
    duration_minutes: int
    max_favorable_pips: float
    max_adverse_pips: float
    breakeven_hit: bool
    partials_taken: List[Dict]


class AccountState(BaseModel):
    """Estado de cuenta para risk engine."""
    balance: float
    equity: float
    daily_pnl: float = 0.0
    monthly_pnl: float = 0.0
    open_positions: List[Position] = Field(default_factory=list)
    daily_trades: int = 0
    consecutive_losses: int = 0
    last_reset_day: Optional[datetime] = None
    last_reset_month: Optional[datetime] = None
    is_blocked: bool = False
    block_reason: str = ""
    
    def can_trade(self, risk_config) -> RiskVerdict:
        """Validación completa pre-trade (delegada a risk_engine)."""
        from backtester.risk_engine import RiskEngine
        engine = RiskEngine(risk_config, self)
        return engine.validate_pre_trade({})  # señal dummy para checks de estado


# ============================================================
# Backtest Results
# ============================================================
class BacktestMetrics(BaseModel):
    """Métricas finales del backtest."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    net_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_usd: float = 0.0
    sharpe_ratio: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    risk_engine_blocks: int = 0
    setup_detection_rate: float = 0.0
    rejection_validation_pass_rate: float = 0.0
    avg_trade_duration_minutes: float = 0.0


class BacktestResult(BaseModel):
    """Resultado completo del backtest."""
    trades: List[ClosedTrade]
    equity_curve: List[Dict]  # [{"timestamp": dt, "equity": float}, ...]
    metrics: BacktestMetrics
    config_snapshot: Dict  # copia de config usada
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float