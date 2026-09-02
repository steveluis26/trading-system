"""Risk Engine: poder de VETO absoluto. Determinista y auditable.
Cada decision se loggea con motivo exacto. Los limites viven en config
versionada (config/risk.yaml), NO hardcodeados."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from core.types import Signal, RiskDecision, Position

@dataclass
class RiskLimits:
    risk_per_trade_pct: float = 1.0
    max_open_positions: int = 3
    max_positions_per_symbol: int = 1
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 15.0
    max_consecutive_losses: int = 5
    min_pips_from_last: float = 15.0      # anti-hedging
    max_spread_points: float = 25.0
    min_risk_reward: float = 1.5
    trading_hours: tuple[int, int] | None = None   # (hora_ini, hora_fin) UTC
    blocked_weekdays: tuple[int, ...] = ()

@dataclass
class AccountState:
    equity: float
    peak_equity: float
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    open_positions: list[Position] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""

class RiskEngine:
    def __init__(self, limits: RiskLimits, pip_size: float = 0.0001,
                 contract_size: float = 100_000):
        self.l = limits
        self.pip = pip_size
        self.contract = contract_size

    def evaluate(self, sig: Signal, acc: AccountState) -> RiskDecision:
        def no(reason: str) -> RiskDecision:
            return RiskDecision(False, reason, correlation_id=sig.correlation_id)

        if acc.halted:
            return no(f"KILL_SWITCH activo: {acc.halt_reason}")

        # --- limites de proteccion (los que salvan la cuenta) ---
        dd = (acc.peak_equity - acc.equity) / acc.peak_equity * 100 if acc.peak_equity else 0
        if dd > self.l.max_drawdown_pct:
            return no(f"Drawdown {dd:.2f}% > {self.l.max_drawdown_pct}%")
        if acc.daily_pnl < 0 and abs(acc.daily_pnl) / acc.equity * 100 > self.l.max_daily_loss_pct:
            return no(f"Perdida diaria excede {self.l.max_daily_loss_pct}%")
        if acc.consecutive_losses >= self.l.max_consecutive_losses:
            return no(f"{acc.consecutive_losses} perdidas consecutivas")

        # --- exposicion ---
        if len(acc.open_positions) >= self.l.max_open_positions:
            return no(f"Max posiciones abiertas ({self.l.max_open_positions})")
        same = [p for p in acc.open_positions if p.signal.symbol == sig.symbol]
        if len(same) >= self.l.max_positions_per_symbol:
            return no(f"Ya hay posicion en {sig.symbol}")

        # --- anti-hedging: distancia minima a operacion previa ---
        for p in same:
            dist = abs(sig.entry - p.open_price) / self.pip
            if dist < self.l.min_pips_from_last:
                return no(f"Anti-Hedging: operacion muy cerca ({dist:.1f} pips). "
                          f"Se requiere min {self.l.min_pips_from_last} pips.")

        # --- calidad de la señal ---
        if sig.risk_reward < self.l.min_risk_reward:
            return no(f"R:R {sig.risk_reward:.2f} < {self.l.min_risk_reward}")
        if sig.context.get("spread", 0) > self.l.max_spread_points:
            return no(f"Spread {sig.context['spread']} > {self.l.max_spread_points}")

        # --- horario ---
        if self.l.trading_hours:
            h0, h1 = self.l.trading_hours
            if not (h0 <= sig.time.hour < h1):
                return no(f"Fuera de horario permitido {h0}-{h1}h")
        if sig.time.weekday() in self.l.blocked_weekdays:
            return no(f"Dia bloqueado: weekday={sig.time.weekday()}")

        # --- sizing: riesgo fijo % sobre distancia real al SL ---
        risk_amount = acc.equity * self.l.risk_per_trade_pct / 100
        sl_dist = abs(sig.entry - sig.sl)
        if sl_dist <= 0:
            return no("SL invalido (distancia cero)")
        vol = round(risk_amount / (sl_dist * self.contract), 2)
        if vol < 0.01:
            return no(f"Volumen calculado {vol} < minimo 0.01")

        return RiskDecision(True, "APPROVED", volume=vol,
                            correlation_id=sig.correlation_id)
