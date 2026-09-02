"""
Trigger Engine - CORE: Validación de rechazo (3 filtros mecánicos) + Double Cross + Volumen
Este es el módulo crítico que implementa las reglas exactas de entrada.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from backtester.models import (
    SweepEvent, TradingSignal, SignalType, Direction, ConfluenceZone, SessionLevels, MarketStructure
)
from backtester.config_loader import get_risk, get_instruments
from backtester.setup_detector import calculate_atr


class TriggerEngine:
    """
    Motor de gatillo - Implementa las 3 condiciones mecánicas de validación de rechazo:
    
    1. PROFUNDIDAD MÁXIMA (ATR Filter): penetración ≤ 1 ATR(14)
    2. ANATOMÍA DE LA VELA (Mecha ≥ 50% FIJO): mecha inferior/superior ≥ 50% rango vela
    3. FACTOR TIEMPO (Reclaim ≤ 2 VELAS): precio cierra del lado correcto en ≤ 2 velas
    
    PLUS:
    - Double Cross: entrada solo en cruce de regreso (market order)
    - Confirmación Volumen: pico de tick volume en vela sweep
    """
    
    def __init__(self, risk_config=None, instruments_config=None):
        self.risk_config = risk_config or get_risk()
        self.instruments = instruments_config or get_instruments()
        self.val_config = self.risk_config.rejection_validation
    
    def validate_rejection(self, sweep: SweepEvent, candles_5m: pd.DataFrame) -> Tuple[bool, str]:
        """
        Valida las 3 condiciones mecánicas de rechazo.
        
        Returns:
            (es_valido, razon_si_no_valido)
        """
        sweep_candle = sweep.sweep_candle
        reclaim_candle = sweep.reclaim_candle
        level = sweep.level
        direction = sweep.direction
        
        # --- CONDICIÓN 1: Profundidad Máxima (ATR Filter) ---
        max_allowed_penetration = sweep.atr_value * self.val_config.max_penetration_atr
        
        if sweep.penetration_pips > max_allowed_penetration:
            return False, (
                f"Penetración {sweep.penetration_pips:.1f} pips > "
                f"1 ATR ({max_allowed_penetration:.1f}) = rompimiento real"
            )
        
        # --- CONDICIÓN 2: Anatomía de la Vela (Mecha ≥ 50% FIJO) ---
        candle_range = sweep_candle["high"] - sweep_candle["low"]
        if candle_range <= 0:
            return False, "Rango de vela sweep = 0"
        
        if direction == Direction.LONG:
            # Mecha inferior = distancia desde low hasta min(open, close)
            lower_wick = min(sweep_candle["open"], sweep_candle["close"]) - sweep_candle["low"]
            wick_ratio = lower_wick / candle_range
        else:  # SHORT
            # Mecha superior = distancia desde max(open, close) hasta high
            upper_wick = sweep_candle["high"] - max(sweep_candle["open"], sweep_candle["close"])
            wick_ratio = upper_wick / candle_range
        
        if wick_ratio < self.val_config.min_wick_ratio:
            return False, (
                f"Mecha ratio {wick_ratio:.2f} < {self.val_config.min_wick_ratio} "
                f"(mín 50% FIJO)"
            )
        
        # --- CONDICIÓN 3: Factor Tiempo (Reclaim en ≤ 2 VELAS MÁXIMO) ---
        candles_to_reclaim = sweep.candles_to_reclaim
        
        if candles_to_reclaim > self.val_config.max_candles_to_reclaim:
            return False, (
                f"Reclaim tomó {candles_to_reclaim} velas > "
                f"{self.val_config.max_candles_to_reclaim} (máx 2) = "
                f"aceptación precio = momentum perdido"
            )
        
        # Validación adicional: cuerpo de vela reclaim debe cerrar DEL LADO CORRECTO del nivel
        if direction == Direction.LONG:
            if reclaim_candle["close"] <= level:
                return False, "Vela reclaim no cierra cuerpo arriba del nivel"
        else:
            if reclaim_candle["close"] >= level:
                return False, "Vela reclaim no cierra cuerpo abajo del nivel"
        
        return True, "Rechazo válido - 3 condiciones cumplidas (mecha ≥50% FIJO, reclaim ≤2 velas)"
    
    def confirm_volume_absorption(
        self, 
        sweep: SweepEvent, 
        candles_5m: pd.DataFrame
    ) -> Tuple[bool, float]:
        """
        Confirma absorción institucional: vela sweep debe tener pico de tick volume.
        
        Returns:
            (confirmado, ratio_volumen)
        """
        if not self.val_config.require_volume_spike:
            return True, 1.0
        
        sweep_idx = sweep.sweep_index
        sweep_candle = candles_5m.iloc[sweep_idx]
        sweep_volume = sweep_candle["tick_volume"]
        
        # Media últimas 20 velas (excluyendo la actual)
        recent_vol = candles_5m["tick_volume"].iloc[max(0, sweep_idx-20):sweep_idx]
        avg_volume = recent_vol.mean() if len(recent_vol) > 0 else 1
        
        volume_ratio = sweep_volume / avg_volume if avg_volume > 0 else 0
        confirmed = volume_ratio >= self.val_config.volume_spike_multiplier
        
        return confirmed, volume_ratio
    
    def check_double_cross_entry(
        self,
        sweep: SweepEvent,
        candles_5m: pd.DataFrame,
        validated: bool,
        volume_confirmed: bool
    ) -> Optional[Dict]:
        """
        Verifica DOBLE CRUCE y genera señal de entrada MARKET.
        
        La entrada se dispara en el OPEN de la vela SIGUIENTE al reclaim confirmado.
        NO usa órdenes limit - solo market order en el cruce de regreso.
        """
        if not (validated and volume_confirmed):
            return None
        
        reclaim_idx = sweep.reclaim_index
        entry_idx = reclaim_idx + 1  # Vela SIGUIENTE al reclaim
        
        if entry_idx >= len(candles_5m):
            return None  # No hay vela siguiente aún (fin de datos)
        
        entry_candle = candles_5m.iloc[entry_idx]
        direction = sweep.direction
        
        return {
            "signal_type": SignalType.ENTRY,
            "direction": direction,
            "entry_price": float(entry_candle["open"]),  # MARKET ORDER al open
            "entry_time": entry_candle["timestamp"],
            "trigger_level": sweep.level,
            "sweep_candle": sweep.sweep_candle,
            "reclaim_candle": sweep.reclaim_candle,
            "validation": {
                "atr_filter": True,
                "wick_ratio": sweep.wick_ratio,
                "time_reclaim": sweep.candles_to_reclaim,
                "volume_spike": volume_confirmed,
                "volume_ratio": sweep.volume_spike
            }
        }
    
    def generate_signal(
        self,
        sweep: SweepEvent,
        candles_5m: pd.DataFrame,
        symbol: str,
        session_levels: SessionLevels,
        market_structure: MarketStructure,
        confluence_zone: ConfluenceZone,
        sl_pips: float
    ) -> Optional[TradingSignal]:
        """
        Pipeline completo: valida rechazo → confirma volumen → verifica double cross → genera señal.
        """
        # 1. Validar rechazo (3 condiciones)
        validated, reason = self.validate_rejection(sweep, candles_5m)
        if not validated:
            return None
        
        # 2. Confirmar volumen
        volume_confirmed, volume_ratio = self.confirm_volume_absorption(sweep, candles_5m)
        if not volume_confirmed:
            return None
        
        # 3. Double cross entry
        entry_data = self.check_double_cross_entry(sweep, candles_5m, validated, volume_confirmed)
        if not entry_data:
            return None
        
        # 4. Calcular SL/TP
        pip_size = self.instruments.pip_to_price.get(symbol, 0.0001)
        tp_pips = sl_pips * self.risk_config.risk_reward.ratio
        
        if sweep.direction == Direction.LONG:
            sl_price = entry_data["entry_price"] - (sl_pips * pip_size)
            tp_price = entry_data["entry_price"] + (tp_pips * pip_size)
        else:
            sl_price = entry_data["entry_price"] + (sl_pips * pip_size)
            tp_price = entry_data["entry_price"] - (tp_pips * pip_size)
        
        # 5. Confianza basada en strength de confluencia
        confidence = min(0.5 + (confluence_zone.strength * 0.15), 0.95)
        
        return TradingSignal(
            signal_type=SignalType.ENTRY,
            direction=sweep.direction,
            symbol=symbol,
            entry_price=entry_data["entry_price"],
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            sl_price=sl_price,
            tp_price=tp_price,
            lot_size=0.0,  # Se calcula en position_simulator
            confidence=confidence,
            timestamp=entry_data["entry_time"],
            trigger_level=sweep.level,
            sweep_event=sweep,
            session_levels=session_levels,
            market_structure=market_structure,
            validation_details={
                "rejection_validated": True,
                "validation_reason": reason,
                "volume_confirmed": volume_confirmed,
                "volume_ratio": volume_ratio,
                "double_cross": True,
                "entry_idx": sweep.reclaim_index + 1
            }
        )


def run_trigger_engine_for_backtest(
    sweeps: List[SweepEvent],
    candles_5m: pd.DataFrame,
    symbol: str,
    session_levels: SessionLevels,
    market_structure: MarketStructure,
    confluence_zones: List[ConfluenceZone],
    sl_pips: float
) -> List[TradingSignal]:
    """
    Ejecuta trigger engine sobre lista de sweeps detectados.
    Retorna señales válidas listas para risk engine.
    """
    engine = TriggerEngine()
    signals = []
    
    for sweep in sweeps:
        # Encontrar zona de confluencia correspondiente
        zone = next((z for z in confluence_zones if abs(z.price - sweep.level) < 0.0001), None)
        if not zone:
            continue
        
        signal = engine.generate_signal(
            sweep, candles_5m, symbol, session_levels, 
            market_structure, zone, sl_pips
        )
        if signal:
            signals.append(signal)
    
    return signals