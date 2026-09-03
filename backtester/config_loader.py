"""Configuration Loader - Carga y valida todos los YAMLs de configuración con Pydantic."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# ============================================================
# RiskConfig sub-models
# ============================================================
class LotSizingConfig(BaseModel):
    mode: str = "fixed_per_1000"
    risk_pct_per_trade: float = 0.01
    lots_per_1000_capital: float = 0.01

class RiskRewardConfig(BaseModel):
    ratio: float = 2.0
    fixed: bool = True
    sl_pips: Dict[str, float] = Field(default_factory=lambda: {"XAUUSD": 45.0, "EURUSD": 20.0, "GBPUSD": 22.0})

class BreakevenConfig(BaseModel):
    enabled: bool = True
    trigger_pct_of_tp: float = 40.0
    close_fraction: float = 33.3

class PartialsConfig(BaseModel):
    enabled: bool = True
    stages: List[Dict[str, float]] = Field(default_factory=lambda: [{"at_pct_of_tp": 40.0, "close_fraction": 0.33}])

class LimitsConfig(BaseModel):
    max_concurrent_trades: int = 2
    max_positions_per_symbol: int = 1
    max_daily_trades: int = 5
    daily_loss_limit_pct: float = 5.0
    monthly_loss_limit_pct: float = 30.0
    max_consecutive_losses: int = 5

class SessionFiltersConfig(BaseModel):
    avoid_high_impact_usd_news: bool = True
    avoid_friday_afternoon: bool = True
    avoid_weekends: bool = True
    london: List[int] = [8, 17]
    newyork: List[int] = [13, 22]

class RejectionValidationConfig(BaseModel):
    min_wick_ratio: float = 0.5
    max_penetration_atr: float = 1.0
    volume_spike_multiplier: float = 1.5

class EntryTriggerConfig(BaseModel):
    require_reaction_candle: bool = True
    max_reclaim_candles: int = 2

class PositionManagementConfig(BaseModel):
    breakeven_at_pct: float = 40.0
    partial_close_fraction: float = 0.33

class KillSwitchConfig(BaseModel):
    daily_loss_pct: float = 5.0
    monthly_loss_pct: float = 30.0
    consecutive_losses: int = 5

class StructureConfig(BaseModel):
    swing_lookback: int = 5
    fvg_min_size_atr: float = 0.2
    trend_lookback_days: int = 30
    min_pivots_for_trend: int = 2

class NewsGuardConfig(BaseModel):
    enabled: bool = True
    window_minutes: int = 15
    widen_sl_atr_mult: float = 1.5

class ConfluenceConfig(BaseModel):
    min_sessions: int = 2
    max_sessions: int = 3
    tolerance_pips: Dict[str, float] = Field(default_factory=lambda: {"XAUUSD": 100, "EURUSD": 10, "GBPUSD": 10})
    weight_multiplier: float = 1.5

class RegimeConfig(BaseModel):
    adx_threshold: float = 25.0
    trend_filter: bool = True

class RiskConfig(BaseModel):
    lot_sizing: LotSizingConfig = LotSizingConfig()
    risk_reward: RiskRewardConfig = RiskRewardConfig()
    breakeven: BreakevenConfig = BreakevenConfig()
    partials: PartialsConfig = PartialsConfig()
    limits: LimitsConfig = LimitsConfig()
    session_filters: SessionFiltersConfig = SessionFiltersConfig()
    rejection_validation: RejectionValidationConfig = RejectionValidationConfig()
    entry_trigger: EntryTriggerConfig = EntryTriggerConfig()
    position_management: PositionManagementConfig = PositionManagementConfig()
    kill_switch: KillSwitchConfig = KillSwitchConfig()
    structure: StructureConfig = StructureConfig()
    news_guard: NewsGuardConfig = NewsGuardConfig()
    regime: RegimeConfig = RegimeConfig()
    confluence: ConfluenceConfig = ConfluenceConfig()


# ============================================================
# Instrument & Session Configs
# ============================================================
class InstrumentSpec(BaseModel):
    pip_size: float
    pip_value_per_lot: float
    spread_typical_pips: float
    contract_size: float = 100000

class InstrumentsConfig(BaseModel):
    instruments: Dict[str, InstrumentSpec] = Field(default_factory=dict)

class SessionConfig(BaseModel):
    start_hour: int
    start_minute: int = 0
    end_hour: int
    end_minute: int = 0

class SessionsConfig(BaseModel):
    timezone: str = "America/Mexico_City"
    sessions: Dict[str, SessionConfig] = Field(default_factory=dict)
    confluence_tolerance_pips: Dict[str, float] = Field(default_factory=lambda: {"XAUUSD": 100, "EURUSD": 10, "GBPUSD": 10})


# ============================================================
# ConfigLoader
# ============================================================
class ConfigLoader:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._risk: Optional[RiskConfig] = None
        self._instruments: Optional[InstrumentsConfig] = None
        self._sessions: Optional[SessionsConfig] = None

    def load_risk(self) -> RiskConfig:
        import yaml
        path = self.config_dir / "risk.yaml"
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._risk = RiskConfig(**data)
        else:
            self._risk = RiskConfig()
        return self._risk

    def load_instruments(self) -> InstrumentsConfig:
        import yaml
        path = self.config_dir / "instruments.yaml"
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._instruments = InstrumentsConfig(**data)
        else:
            self._instruments = InstrumentsConfig()
        return self._instruments

    def load_sessions(self) -> SessionsConfig:
        import yaml
        path = self.config_dir / "sessions.yaml"
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._sessions = SessionsConfig(**data)
        else:
            self._sessions = SessionsConfig()
        return self._sessions

    def get_risk(self) -> RiskConfig:
        if self._risk is None:
            return self.load_risk()
        return self._risk

    def get_instruments(self) -> InstrumentsConfig:
        if self._instruments is None:
            return self.load_instruments()
        return self._instruments

    def get_sessions(self) -> SessionsConfig:
        if self._sessions is None:
            return self.load_sessions()
        return self._sessions


# Singleton
_loader: Optional[ConfigLoader] = None

def get_loader(config_dir: str = "config") -> ConfigLoader:
    global _loader
    if _loader is None:
        _loader = ConfigLoader(config_dir)
    return _loader

def get_risk() -> RiskConfig:
    return get_loader().get_risk()

def get_instruments() -> InstrumentsConfig:
    return get_loader().get_instruments()

def get_sessions() -> SessionsConfig:
    return get_loader().get_sessions()