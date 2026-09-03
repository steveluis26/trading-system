"""
Configuration Loader - Carga y valida todos los YAMLs de configuración
Usa Pydantic para tipado estricto y validación automática.
"""
from pathlib import Path
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import yaml


# ============================================================
# Models para config/instruments.yaml
# ============================================================
class InstrumentSpec(BaseModel):
    name: str
    pip_size: float
    pip_value_per_lot: float
    contract_size: int
    lot_step: float
    min_lot: float
    max_lot: float
    swap_long: float
    swap_short: float
    spread_typical_pips: float
    margin_currency: str
    digits: int
    category: str


class RoundingConfig(BaseModel):
    price_digits: int
    lot_digits: int
    pnl_digits: int


class InstrumentsConfig(BaseModel):
    instruments: Dict[str, InstrumentSpec]
    rounding: RoundingConfig
    pip_to_price: Dict[str, float]
    pip_value_usd_per_standard_lot: Dict[str, float]


# ============================================================
# Models para config/sessions.yaml
# ============================================================
class SessionConfig(BaseModel):
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    crosses_midnight: bool
    description: str


class VisualizationConfig(BaseModel):
    show_session_boxes: bool
    show_confluence_zones: bool
    zone_opacity: float
    colors: Dict[str, str]


class SessionsConfig(BaseModel):
    timezone: str
    sessions: Dict[str, SessionConfig]
    confluence_tolerance_pips: Dict[str, int]
    visualization: VisualizationConfig
    holidays_calendar: str


# ============================================================
# Models para config/risk.yaml
# ============================================================
class LotSizingConfig(BaseModel):
    mode: Literal["pct_risk", "fixed_lot"]
    risk_pct_per_trade: float = 0.01
    lots_per_1000_capital: float = 0.01


class RiskRewardConfig(BaseModel):
    ratio: float
    fixed: bool


class BreakevenConfig(BaseModel):
    enabled: bool
    trigger_pct_of_tp: float
    move_sl_to_entry: bool


class PartialStage(BaseModel):
    at_pct_of_tp: float
    close_fraction: float


class PartialsConfig(BaseModel):
    enabled: bool
    stages: List[PartialStage]


class LimitsConfig(BaseModel):
    max_concurrent_trades: int
    max_daily_trades: int
    daily_loss_limit_pct: float
    monthly_loss_limit_pct: float
    max_consecutive_losses: int
    reactivation: str
    scope: Literal["per_account", "aggregated"]


class SessionFiltersConfig(BaseModel):
    avoid_friday_afternoon: bool
    avoid_weekends: bool
    avoid_high_impact_usd_news: bool


class RejectionValidationConfig(BaseModel):
    atr_period: int
    max_penetration_atr: float
    min_wick_ratio: float
    max_candles_to_reclaim: int
    require_volume_spike: bool
    volume_spike_multiplier: float


class EntryTriggerConfig(BaseModel):
    type: Literal["market", "limit"]
    double_cross_required: bool


class PositionManagementConfig(BaseModel):
    trailing_stop: bool
    close_on_friday: bool
    close_on_connection_loss: bool


class KillSwitchConfig(BaseModel):
    daily_loss_pct: float
    monthly_loss_pct: float
    consecutive_losses: int
    reactivation: str


class StructureConfig(BaseModel):
    macro_timeframes: List[str]
    setup_timeframe: str
    entry_timeframe: str
    trend_lookback_days: int
    min_pivots_for_trend: int


class ConfluenceConfig(BaseModel):
    min_sessions: int
    max_sessions: int
    tolerance_pips: Dict[str, int]
    weight_multiplier: float


class NewsFilterConfig(BaseModel):
    lookahead_hours: int
    currencies: List[str]
    impacts: List[str]
    calendar_source: str
    avoid_high_impact_usd_news: bool = True


class RiskConfig(BaseModel):
    lot_sizing: LotSizingConfig
    risk_reward: RiskRewardConfig
    breakeven: BreakevenConfig
    partials: PartialsConfig
    limits: LimitsConfig
    session_filters: SessionFiltersConfig
    rejection_validation: RejectionValidationConfig
    entry_trigger: EntryTriggerConfig
    position_management: PositionManagementConfig
    kill_switch: KillSwitchConfig
    structure: StructureConfig
    confluence: ConfluenceConfig
    news_filter: NewsFilterConfig


# ============================================================
# Loader principal
# ============================================================
class ConfigLoader:
    """Carga única de toda la configuración del sistema."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._instruments: Optional[InstrumentsConfig] = None
        self._sessions: Optional[SessionsConfig] = None
        self._risk: Optional[RiskConfig] = None
    
    def load_instruments(self) -> InstrumentsConfig:
        if self._instruments is None:
            with open(self.config_dir / "instruments.yaml") as f:
                data = yaml.safe_load(f)
            self._instruments = InstrumentsConfig(**data)
        return self._instruments
    
    def load_sessions(self) -> SessionsConfig:
        if self._sessions is None:
            with open(self.config_dir / "sessions.yaml") as f:
                data = yaml.safe_load(f)
            self._sessions = SessionsConfig(**data)
        return self._sessions
    
    def load_risk(self) -> RiskConfig:
        if self._risk is None:
            with open(self.config_dir / "risk.yaml") as f:
                data = yaml.safe_load(f)
            self._risk = RiskConfig(**data)
        return self._risk
    
    def load_all(self) -> tuple[InstrumentsConfig, SessionsConfig, RiskConfig]:
        return (self.load_instruments(), self.load_sessions(), self.load_risk())


# Instancia global para uso fácil
config_loader = ConfigLoader()


def get_instruments() -> InstrumentsConfig:
    return config_loader.load_instruments()


def get_sessions() -> SessionsConfig:
    return config_loader.load_sessions()


def get_risk() -> RiskConfig:
    return config_loader.load_risk()