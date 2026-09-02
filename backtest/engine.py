"""Backtester EVENT-DRIVEN.

Por que no vectorbt/backtesting.py:
  1. SL/TP intrabar: con solo OHLC no sabes si toco SL o TP primero.
     Aqui se resuelve explicitamente y de forma PESIMISTA (asume SL primero
     cuando la vela toca ambos). Un vectorizado te regala el TP -> backtest falso.
  2. Filtros con estado (anti-hedging, max posiciones) dependen del orden
     de los eventos. Vectorizado no lo modela.
  3. Lotaje dinamico segun equity actual.

Garantia anti-leakage: la estrategia recibe SOLO history[:i+1]. Es
estructuralmente imposible que vea el futuro.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from core.types import Bar, Side, Position, Signal
from strategies.base import Strategy
from risk.engine import RiskEngine, AccountState, RiskLimits

@dataclass
class Costs:
    """Costos reales. Sin esto el backtest es ficcion."""
    spread_points: float = 12.0        # fallback si el Bar no trae spread
    commission_per_lot: float = 7.0    # round-turn USD
    slippage_points: float = 3.0       # pesimista
    swap_per_lot_per_day: float = -2.0
    point: float = 0.00001
    contract_size: float = 100_000

@dataclass
class BacktestResult:
    positions: list[Position] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    equity: list[tuple] = field(default_factory=list)
    initial: float = 10_000.0

class Backtester:
    def __init__(self, strategy: Strategy, risk: RiskEngine, costs: Costs,
                 initial_equity: float = 10_000.0):
        self.s = strategy; self.r = risk; self.c = costs
        self.initial = initial_equity

    def run(self, bars: list[Bar]) -> BacktestResult:
        res = BacktestResult(initial=self.initial)
        acc = AccountState(equity=self.initial, peak_equity=self.initial)
        self.s.reset()
        day = None

        for i, bar in enumerate(bars):
            if day != bar.time.date():          # reset de limites diarios
                day = bar.time.date()
                acc.daily_pnl = 0.0
                # el streak de perdidas pausa el DIA, no la vida del sistema:
                # sin este reset el veto se vuelve permanente (deadlock).
                acc.consecutive_losses = 0

            # 1) gestionar posiciones abiertas ANTES de abrir nuevas
            self._manage(acc, bar, res)

            # 2) la estrategia solo ve el pasado
            sig = self.s.on_bar(bar, bars[:i+1])
            if sig is None:
                res.equity.append((bar.time, acc.equity)); continue

            # 3) risk engine con veto
            dec = self.r.evaluate(sig, acc)
            if not dec.approved:
                res.rejections.append({"time": bar.time, "reason": dec.reason,
                                       "strategy": sig.strategy,
                                       "correlation_id": sig.correlation_id})
                res.equity.append((bar.time, acc.equity)); continue

            # 4) fill con spread + slippage EN CONTRA
            spread = (bar.spread or self.c.spread_points) * self.c.point
            slip = self.c.slippage_points * self.c.point
            fill = sig.entry + spread/2 + slip if sig.side is Side.BUY \
                   else sig.entry - spread/2 - slip
            comm = -self.c.commission_per_lot * dec.volume
            pos = Position(signal=sig, volume=dec.volume, open_time=bar.time,
                           open_price=fill, commission=comm)
            acc.open_positions.append(pos)
            res.equity.append((bar.time, acc.equity))

        # cerrar lo que quede al final del periodo
        if bars:
            for p in list(acc.open_positions):
                self._close(acc, p, bars[-1].close, bars[-1].time, "end_of_data", res)
        return res

    def _manage(self, acc: AccountState, bar: Bar, res: BacktestResult) -> None:
        for p in list(acc.open_positions):
            sl, tp = p.signal.sl, p.signal.tp
            hit_sl = bar.low <= sl if p.signal.side is Side.BUY else bar.high >= sl
            hit_tp = bar.high >= tp if p.signal.side is Side.BUY else bar.low <= tp
            # PESIMISTA: si la vela toca ambos, asumimos SL primero
            if hit_sl:
                self._close(acc, p, sl, bar.time, "sl", res)
            elif hit_tp:
                self._close(acc, p, tp, bar.time, "tp", res)
            else:
                days = max((bar.time - p.open_time).days, 0)
                p.swap = self.c.swap_per_lot_per_day * p.volume * days

    def _close(self, acc, p: Position, price: float, t, reason: str,
               res: BacktestResult) -> None:
        spread = self.c.spread_points * self.c.point
        p.close_price = price - spread/2 if p.signal.side is Side.BUY else price + spread/2
        p.close_time = t; p.close_reason = reason
        pnl = p.pnl(self.c.contract_size)
        acc.equity += pnl
        acc.daily_pnl += pnl
        acc.peak_equity = max(acc.peak_equity, acc.equity)
        acc.consecutive_losses = acc.consecutive_losses + 1 if pnl < 0 else 0
        acc.open_positions.remove(p)
        res.positions.append(p)
