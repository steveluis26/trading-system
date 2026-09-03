"""Carga config/risk.yaml en un dataclass tipado.
Centraliza TODOS los limites (vienen de la encuesta + 7 aclaraciones)."""
from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskConfig:
    # sizing (formula de LOTES confirmada por ella)
    lots_per_1000_capital: float = 0.01
    max_risk_per_trade_pct_softcap: float = 2.5

    # limites operativos
    max_open_positions: int = 2
    max_positions_per_symbol: int = 1
    max_operations_per_day: int = 5
    max_daily_loss_pct: float = 5.0
    kill_switch_dd_pct: float = 30.0           # mensual -> STOP total
    max_consecutive_losses: int = 5            # 5 perdedoras => BLOQUEO total
    reentry_same_zone: bool = False

    # sesiones (UTC)
    session_london: tuple[int, int] = (8, 17)
    session_newyork: tuple[int, int] = (13, 22)
    no_trade_weekday: int = 4                  # viernes
    no_hold_over_weekend: bool = True
    news_filter: bool = False                  # sin calendario en backtest v1

    # salida
    be_trigger_pct_to_tp: float = 40.0
    be_close_fraction: float = 33.3
    rr_target: list[float] = field(default_factory=lambda: [2.0, 3.0])

    # costos
    spread_points: dict = field(default_factory=dict)
    commission_per_lot: float = 7.0
    slippage_points: float = 3.0
    swap_per_lot_per_day: float = -2.0

    # por simbolo
    pip_size: dict = field(default_factory=lambda: {"EURUSD": 0.0001, "GBPUSD": 0.0001, "XAUUSD": 0.01})
    contract_size: dict = field(default_factory=lambda: {"EURUSD": 100_000, "GBPUSD": 100_000, "XAUUSD": 100})
    # USD por pip por lote (SEGUN ELLA: oro 0.01 lote = $1/pip, forex 0.01 lote = $0.10/pip)
    usd_per_pip_per_lot: dict = field(default_factory=lambda: {"EURUSD": 10.0, "GBPUSD": 10.0, "XAUUSD": 1.0})
    spread_default: dict = field(default_factory=lambda: {"EURUSD": 12.0, "GBPUSD": 18.0, "XAUUSD": 35.0})

    @staticmethod
    def from_yaml(path: str = "config/risk.yaml") -> "RiskConfig":
        with open(path) as f:
            d = yaml.safe_load(f)
        c = RiskConfig()
        ls = d.get("lot_sizing", {})
        c.lots_per_1000_capital = ls.get("lots_per_1000_capital", d.get("lots_per_1000_capital", c.lots_per_1000_capital))
        lim = d.get("limits", {})
        c.max_risk_per_trade_pct_softcap = d.get("max_risk_per_trade_pct_softcap", c.max_risk_per_trade_pct_softcap)
        op = lim.get("max_concurrent_trades", d.get("max_open_positions", c.max_open_positions))
        c.max_open_positions = op
        c.max_positions_per_symbol = lim.get("max_positions_per_symbol", d.get("max_positions_per_symbol", c.max_positions_per_symbol))
        c.max_operations_per_day = lim.get("max_daily_trades", d.get("max_operations_per_day", c.max_operations_per_day))
        c.max_daily_loss_pct = lim.get("daily_loss_limit_pct", d.get("max_daily_loss_pct", c.max_daily_loss_pct))
        c.kill_switch_dd_pct = lim.get("monthly_loss_limit_pct", d.get("kill_switch_dd_pct", lim.get("monthly_loss_limit_pct", c.kill_switch_dd_pct)))
        c.max_consecutive_losses = lim.get("max_consecutive_losses", d.get("max_consecutive_losses", c.max_consecutive_losses))
        c.reentry_same_zone = d.get("reentry_same_zone", c.reentry_same_zone)

        s = d.get("session_filters", d.get("sessions", {}))
        if "london" in s:
            c.session_london = tuple(s.get("london", list(c.session_london)))
        if "newyork" in s:
            c.session_newyork = tuple(s.get("newyork", list(c.session_newyork)))
        c.no_trade_weekday = d.get("no_trade_weekday", 4 if d.get("session_filters", {}).get("avoid_friday_afternoon") else c.no_trade_weekday)
        c.no_hold_over_weekend = d.get("no_hold_over_weekend", True if d.get("session_filters", {}).get("avoid_weekends") else c.no_hold_over_weekend)
        c.news_filter = bool(d.get("news_filter")) and str(d.get("news_filter")) not in ("false", "no")
        if d.get("session_filters", {}).get("avoid_high_impact_usd_news"):
            c.news_filter = True

        be = d.get("breakeven", d.get("breakeven_partial", {}))
        c.be_trigger_pct_to_tp = be.get("trigger_pct_of_tp", be.get("trigger_pct_to_tp", c.be_trigger_pct_to_tp))
        c.be_close_fraction = be.get("close_fraction", c.be_close_fraction)
        rr = d.get("risk_reward", {})
        c.rr_target = [rr.get("ratio", c.rr_target[0])] if "ratio" in rr else d.get("rr_target", c.rr_target)

        co = d.get("costs", {})
        c.spread_points = co.get("spread_points", {})
        c.commission_per_lot = co.get("commission_per_lot", c.commission_per_lot)
        c.slippage_points = co.get("slippage_points", c.slippage_points)
        c.swap_per_lot_per_day = co.get("swap_per_lot_per_day", c.swap_per_lot_per_day)
        return c

    def spread(self, symbol: str, default=12.0) -> float:
        return float(self.spread_points.get(symbol, self.spread_default.get(symbol, default)))

    def pip(self, symbol: str) -> float:
        return float(self.pip_size.get(symbol, 0.0001))

    def contract(self, symbol: str) -> float:
        return float(self.contract_size.get(symbol, 100_000))

    def usd_per_pip(self, symbol: str) -> float:
        return float(self.usd_per_pip_per_lot.get(symbol, 10.0))

    def in_session(self, hour: int) -> bool:
        a, b = self.session_london
        c, e = self.session_newyork
        return (a <= hour < b) or (c <= hour < e)
