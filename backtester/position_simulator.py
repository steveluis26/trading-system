"""
Position Simulator - Simula gestión de posición: sizing 1%, SL/TP 1:2, breakeven 40%, parciales
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import uuid
from backtester.models import (
    TradingSignal, Position, ClosedTrade, Direction, SignalType, AccountState
)
from backtester.config_loader import get_risk, get_instruments


class PositionSimulator:
    """
    Simula el ciclo de vida completo de una posición:
    - Cálculo de lote (1% riesgo dinámico)
    - SL/TP fijo 1:2
    - Breakeven al 40% del camino al TP
    - Parciales al 40% (cierra ~33% del lote)
    - Cierre por SL, TP, breakeven, viernes, manual
    """
    
    def __init__(self, risk_config=None, instruments_config=None):
        self.risk_config = risk_config or get_risk()
        self.instruments = instruments_config or get_instruments()
        self.rr_ratio = self.risk_config.risk_reward.ratio
        self.breakeven_pct = self.risk_config.breakeven.trigger_pct_of_tp
        self.partial_stages = self.risk_config.partials.stages
    
    def calculate_lot_size(
        self, 
        balance: float, 
        sl_pips: float, 
        symbol: str,
        risk_pct: float = None
    ) -> float:
        """
        Lote = (Balance × risk_pct) / (SL_pips × Valor_Pip_Por_Lote)
        Redondeado al step del broker.
        """
        risk_pct = risk_pct or self.risk_config.lot_sizing.risk_pct_per_trade
        pip_value = self.instruments.pip_value_usd_per_standard_lot.get(symbol, 10.0)
        
        risk_amount = balance * risk_pct
        raw_lot = risk_amount / (sl_pips * pip_value)
        
        # Redondear al step del broker
        step = self.instruments.instruments[symbol].lot_step
        lot = round(raw_lot / step) * step
        
        # Aplicar límites
        min_lot = self.instruments.instruments[symbol].min_lot
        max_lot = self.instruments.instruments[symbol].max_lot
        lot = max(min_lot, min(lot, max_lot))
        
        return lot
    
    def calculate_sl_tp_prices(
        self, 
        entry_price: float, 
        direction: Direction, 
        sl_pips: float, 
        symbol: str
    ) -> Tuple[float, float]:
        """Calcula precios SL y TP (R:R fijo 1:2)."""
        pip_size = self.instruments.pip_to_price.get(symbol, 0.0001)
        tp_pips = sl_pips * self.rr_ratio
        
        if direction == Direction.LONG:
            sl = entry_price - (sl_pips * pip_size)
            tp = entry_price + (tp_pips * pip_size)
        else:
            sl = entry_price + (sl_pips * pip_size)
            tp = entry_price - (tp_pips * pip_size)
        
        # Redondear a dígitos del instrumento
        digits = self.instruments.instruments[symbol].digits
        return round(sl, digits), round(tp, digits)
    
    def open_position(
        self, 
        signal: TradingSignal, 
        account_balance: float
    ) -> Position:
        """Crea posición desde señal válida."""
        # Calcular lote
        lot = self.calculate_lot_size(account_balance, signal.sl_pips, signal.symbol)
        
        # Recalcular SL/TP exactos con lote final
        sl_price, tp_price = self.calculate_sl_tp_prices(
            signal.entry_price, signal.direction, signal.sl_pips, signal.symbol
        )
        
        pip_value = self.instruments.pip_value_usd_per_standard_lot.get(signal.symbol, 10.0)
        risk_amount = lot * signal.sl_pips * pip_value
        
        position = Position(
            id=str(uuid.uuid4())[:8],
            signal=signal,
            entry_time=signal.timestamp,
            entry_price=signal.entry_price,
            current_sl=sl_price,
            current_tp=tp_price,
            lot_size=lot,
            direction=signal.direction,
            symbol=signal.symbol,
            status="OPEN"
        )
        
        # Agregar info de riesgo a la señal
        signal.lot_size = lot
        signal.sl_price = sl_price
        signal.tp_price = tp_price
        signal.risk_amount_usd = risk_amount
        
        return position
    
    def update_position(
        self, 
        position: Position, 
        current_candle: pd.Series,
        current_time: datetime
    ) -> List[Dict]:
        """
        Actualiza posición con vela actual.
        Retorna lista de acciones: [{action, price, reason, lot}, ...]
        """
        actions = []
        high = current_candle["high"]
        low = current_candle["low"]
        close = current_candle["close"]
        
        # Actualizar max favorable/adverse
        if position.direction == Direction.LONG:
            favorable_pips = (high - position.entry_price) / self.instruments.pip_to_price.get(position.symbol, 0.0001)
            adverse_pips = (position.entry_price - low) / self.instruments.pip_to_price.get(position.symbol, 0.0001)
        else:
            favorable_pips = (position.entry_price - low) / self.instruments.pip_to_price.get(position.symbol, 0.0001)
            adverse_pips = (high - position.entry_price) / self.instruments.pip_to_price.get(position.symbol, 0.0001)
        
        position.max_favorable_pips = max(position.max_favorable_pips, favorable_pips)
        position.max_adverse_pips = max(position.max_adverse_pips, adverse_pips)
        
        # 1. Check SL hit
        if position.direction == Direction.LONG:
            if low <= position.current_sl:
                actions.append({
                    "action": "CLOSE_SL",
                    "price": position.current_sl,
                    "reason": "Stop Loss hit",
                    "lot": position.lot_size,
                    "time": current_time
                })
                position.status = "CLOSED"
                return actions
        else:
            if high >= position.current_sl:
                actions.append({
                    "action": "CLOSE_SL",
                    "price": position.current_sl,
                    "reason": "Stop Loss hit",
                    "lot": position.lot_size,
                    "time": current_time
                })
                position.status = "CLOSED"
                return actions
        
        # 2. Check TP hit
        if position.direction == Direction.LONG:
            if high >= position.current_tp:
                actions.append({
                    "action": "CLOSE_TP",
                    "price": position.current_tp,
                    "reason": "Take Profit hit",
                    "lot": position.lot_size,
                    "time": current_time
                })
                position.status = "CLOSED"
                return actions
        else:
            if low <= position.current_tp:
                actions.append({
                    "action": "CLOSE_TP",
                    "price": position.current_tp,
                    "reason": "Take Profit hit",
                    "lot": position.lot_size,
                    "time": current_time
                })
                position.status = "CLOSED"
                return actions
        
        # 3. Check Breakeven (40% del camino al TP)
        if not position.breakeven_triggered:
            be_triggered = self._check_breakeven(position, close)
            if be_triggered:
                position.current_sl = position.entry_price  # SL → entry (breakeven real)
                position.breakeven_triggered = True
                actions.append({
                    "action": "MOVE_SL_BE",
                    "price": position.entry_price,
                    "reason": f"Breakeven at {self.breakeven_pct*100}% TP",
                    "lot": 0,
                    "time": current_time
                })
        
        # 4. Check Parciales (al 40% TP, cierra ~33%)
        for stage in self.partial_stages:
            stage_key = f"partial_{stage.at_pct_of_tp}"
            if stage_key not in position.partials_executed:
                if self._check_partial(position, close, stage.at_pct_of_tp):
                    close_lot = position.lot_size * stage.close_fraction
                    # Redondear lote
                    step = self.instruments.instruments[position.symbol].lot_step
                    close_lot = round(close_lot / step) * step
                    close_lot = max(close_lot, step)
                    
                    if close_lot < position.lot_size:
                        position.lot_size -= close_lot
                        position.partials_executed.append(stage_key)
                        position.status = "PARTIAL"
                        
                        actions.append({
                            "action": "PARTIAL_CLOSE",
                            "price": close,  # Precio actual aprox
                            "reason": f"Partial at {stage.at_pct_of_tp*100}% TP",
                            "lot": close_lot,
                            "time": current_time
                        })
        
        return actions
    
    def _check_breakeven(self, position: Position, current_price: float) -> bool:
        """Verifica si precio alcanzó 40% del camino al TP."""
        entry = position.entry_price
        tp = position.current_tp
        
        if position.direction == Direction.LONG:
            distance_to_tp = tp - entry
            current_progress = current_price - entry
        else:
            distance_to_tp = entry - tp
            current_progress = entry - current_price
        
        if distance_to_tp <= 0:
            return False
        
        return (current_progress / distance_to_tp) >= self.breakeven_pct
    
    def _check_partial(self, position: Position, current_price: float, at_pct: float) -> bool:
        """Verifica si precio alcanzó % del camino al TP para parcial."""
        entry = position.entry_price
        tp = position.current_tp
        
        if position.direction == Direction.LONG:
            distance_to_tp = tp - entry
            current_progress = current_price - entry
        else:
            distance_to_tp = entry - tp
            current_progress = entry - current_price
        
        if distance_to_tp <= 0:
            return False
        
        return (current_progress / distance_to_tp) >= at_pct
    
    def force_close_friday(self, position: Position, friday_close_price: float, friday_time: datetime) -> Dict:
        """Cierre forzado viernes (config: close_on_friday)."""
        return {
            "action": "CLOSE_FRIDAY",
            "price": friday_close_price,
            "reason": "Friday close - risk management",
            "lot": position.lot_size,
            "time": friday_time
        }
    
    def calculate_pnl(
        self, 
        position: Position, 
        exit_price: float, 
        exit_lot: float
    ) -> Tuple[float, float]:
        """Calcula P&L en USD y pips para un cierre parcial/total."""
        pip_size = self.instruments.pip_to_price.get(position.symbol, 0.0001)
        pip_value = self.instruments.pip_value_usd_per_standard_lot.get(position.symbol, 10.0)
        
        if position.direction == Direction.LONG:
            pips = (exit_price - position.entry_price) / pip_size
        else:
            pips = (position.entry_price - exit_price) / pip_size
        
        pnl_usd = pips * pip_value * exit_lot
        return pnl_usd, pips
    
    def close_position(
        self,
        position: Position,
        exit_price: float,
        exit_reason: SignalType,
        exit_time: datetime,
        exit_lot: float = None
    ) -> ClosedTrade:
        """Cierra posición y genera ClosedTrade completo."""
        exit_lot = exit_lot or position.lot_size
        pnl_usd, pnl_pips = self.calculate_pnl(position, exit_price, exit_lot)
        
        duration = (exit_time - position.entry_time).total_seconds() / 60
        
        trade = ClosedTrade(
            position=position,
            exit_time=exit_time,
            exit_price=exit_price,
            exit_reason=exit_reason,
            pnl_usd=pnl_usd,
            pnl_pips=pnl_pips,
            duration_minutes=int(duration),
            max_favorable_pips=position.max_favorable_pips,
            max_adverse_pips=position.max_adverse_pips,
            breakeven_hit=position.breakeven_triggered,
            partials_taken=position.partials_executed.copy()
        )
        
        return trade


def simulate_position_lifecycle(
    signal: TradingSignal,
    candles_5m: pd.DataFrame,
    account_balance: float,
    risk_config=None,
    instruments_config=None
) -> Tuple[ClosedTrade, pd.DataFrame]:
    """
    Simula ciclo completo de una posición desde entrada hasta salida.
    Retorna (ClosedTrade, DataFrame con equity curve points).
    """
    sim = PositionSimulator(risk_config, instruments_config)
    position = sim.open_position(signal, account_balance)
    
    equity_points = []
    current_balance = account_balance
    
    # Iterar velas desde entry_idx + 1
    entry_idx = signal.validation_details.get("entry_idx", 0)
    
    for i in range(entry_idx + 1, len(candles_5m)):
        candle = candles_5m.iloc[i]
        current_time = candle["timestamp"]
        
        # Verificar cierre viernes (16:00 México = cierre NY)
        if current_time.hour >= 16 and current_time.weekday() == 4:  # Viernes 16:00+
            close_action = sim.force_close_friday(position, candle["close"], current_time)
            trade = sim.close_position(position, close_action["price"], SignalType.EXIT_FRIDAY_CLOSE, current_time)
            current_balance += trade.pnl_usd
            equity_points.append({"timestamp": current_time, "equity": current_balance, "trade_id": position.id})
            return trade, pd.DataFrame(equity_points)
        
        # Actualizar posición
        actions = sim.update_position(position, candle, current_time)
        
        for action in actions:
            if action["action"] in ["CLOSE_SL", "CLOSE_TP", "CLOSE_FRIDAY"]:
                trade = sim.close_position(
                    position, action["price"], 
                    SignalType[action["action"]], action["time"], action["lot"]
                )
                current_balance += trade.pnl_usd
                equity_points.append({"timestamp": action["time"], "equity": current_balance, "trade_id": position.id})
                return trade, pd.DataFrame(equity_points)
            
            elif action["action"] == "PARTIAL_CLOSE":
                # Parcial: actualizar balance pero posición sigue abierta
                pnl_usd, _ = sim.calculate_pnl(position, action["price"], action["lot"])
                current_balance += pnl_usd
                equity_points.append({"timestamp": action["time"], "equity": current_balance, "trade_id": position.id})
            
            elif action["action"] == "MOVE_SL_BE":
                equity_points.append({"timestamp": action["time"], "equity": current_balance, "trade_id": position.id})
    
    # Si llega al final de datos sin cerrar
    last_candle = candles_5m.iloc[-1]
    trade = sim.close_position(position, last_candle["close"], SignalType.EXIT_MANUAL, last_candle["timestamp"])
    current_balance += trade.pnl_usd
    equity_points.append({"timestamp": last_candle["timestamp"], "equity": current_balance, "trade_id": position.id})
    
    return trade, pd.DataFrame(equity_points)