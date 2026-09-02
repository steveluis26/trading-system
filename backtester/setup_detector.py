"""
Setup Detector - Identifica zonas de confluencia y detecta barridos (sweeps) en 15M/5M
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from backtester.models import (
    ConfluenceZone, SweepEvent, Direction, SessionLevels, SessionName, TradingSignal, SignalType
)
from backtester.config_loader import get_risk, get_instruments


class SetupDetector:
    """
    Detecta setups válidos:
    1. Zona de confluencia (2-3 sesiones) en dirección de tendencia macro
    2. Barrido de liquidez (sweep) en 5M con rechazo válido
    """
    
    def __init__(self, risk_config=None, instruments_config=None):
        self.risk_config = risk_config or get_risk()
        self.instruments = instruments_config or get_instruments()
        self.min_sessions = self.risk_config.confluence.min_sessions
        self.max_sessions = self.risk_config.confluence.max_sessions
    
    def find_setup_zone(
        self,
        confluence_zones: List[ConfluenceZone],
        macro_trend: str,
        current_price: float
    ) -> Optional[ConfluenceZone]:
        """
        Filtra zonas de confluencia por dirección de tendencia macro.
        
        BULLISH → busca zonas de SOPORTE (is_low = True) por debajo del precio
        BEARISH → busca zonas de RESISTENCIA (is_high = True) por encima del precio
        """
        if macro_trend == "BULLISH":
            # Zonas de soporte (lows confluentes) por debajo del precio actual
            candidates = [z for z in confluence_zones if z.is_low and z.price <= current_price * 1.001]
        elif macro_trend == "BEARISH":
            # Zonas de resistencia (highs confluentes) por encima del precio actual
            candidates = [z for z in confluence_zones if z.is_high and z.price >= current_price * 0.999]
        else:
            return None
        
        if not candidates:
            return None
        
        # Retornar la más fuerte (strength 3 > 2) y más cercana al precio
        # Scoring: strength * 100 - distancia_pips
        def score_zone(z: ConfluenceZone) -> float:
            pip_size = self.instruments.pip_to_price.get("XAUUSD", 0.01)  # default
            dist_pips = abs(current_price - z.price) / pip_size
            return z.strength * 100 - dist_pips
        
        return max(candidates, key=score_zone)
    
    def detect_sweep_5m(
        self,
        candles_5m: pd.DataFrame,
        zone: ConfluenceZone,
        macro_direction: Direction,
        start_idx: int = 0
    ) -> Optional[SweepEvent]:
        """
        Detecta barrido de liquidez en 5M en la zona de confluencia.
        
        LONG: precio rompe LOW de zona hacia abajo y regresa (cierra arriba)
        SHORT: precio rompe HIGH de zona hacia arriba y regresa (cierra abajo)
        
        Args:
            candles_5m: DataFrame 5M con [timestamp, open, high, low, close, tick_volume]
            zone: ConfluenceZone detectada
            macro_direction: Direction.LONG o Direction.SHORT
            start_idx: Índice desde donde buscar (evitar look-ahead)
            
        Returns:
            SweepEvent si detecta barrido, None si no
        """
        level = zone.price
        direction = macro_direction
        
        # Iterar desde start_idx buscando patrón sweep + reclaim
        for i in range(start_idx + 1, len(candles_5m)):
            prev_candle = candles_5m.iloc[i - 1]
            curr_candle = candles_5m.iloc[i]
            
            if direction == Direction.LONG:
                # Barrido: low anterior rompe nivel
                swept = prev_candle["low"] < level
                # Reclaim: vela actual cierra ARRIBA del nivel
                reclaimed = curr_candle["close"] > level
            else:  # SHORT
                swept = prev_candle["high"] > level
                reclaimed = curr_candle["close"] < level
            
            if swept and reclaimed:
                # Calcular métricas del sweep
                if direction == Direction.LONG:
                    penetration = level - prev_candle["low"]
                    # Mecha inferior de vela sweep
                    lower_wick = min(prev_candle["open"], prev_candle["close"]) - prev_candle["low"]
                    candle_range = prev_candle["high"] - prev_candle["low"]
                else:
                    penetration = prev_candle["high"] - level
                    # Mecha superior de vela sweep
                    upper_wick = prev_candle["high"] - max(prev_candle["open"], prev_candle["close"])
                    candle_range = prev_candle["high"] - prev_candle["low"]
                
                wick_ratio = (lower_wick if direction == Direction.LONG else upper_wick) / candle_range if candle_range > 0 else 0
                candles_to_reclaim = 1  # i - (i-1) = 1
                
                return SweepEvent(
                    sweep_candle=prev_candle.to_dict(),
                    reclaim_candle=curr_candle.to_dict(),
                    sweep_index=i - 1,
                    reclaim_index=i,
                    level=level,
                    direction=direction,
                    penetration_pips=penetration / self.instruments.pip_to_price.get("XAUUSD", 0.01),
                    wick_ratio=wick_ratio,
                    candles_to_reclaim=candles_to_reclaim,
                    volume_spike=False,  # Se valida en trigger_engine
                    atr_value=0.0,  # Se calcula en trigger_engine
                    validation_passed=False,
                    validation_reason=""
                )
        
        return None
    
    def scan_for_sweeps(
        self,
        candles_5m: pd.DataFrame,
        zones: List[ConfluenceZone],
        macro_direction: Direction,
        atr_values: pd.Series,  # ATR(14) alineado con candles_5m
        volume_threshold: float = 1.5
    ) -> List[SweepEvent]:
        """
        Escanea todas las zonas buscando sweeps válidos con validación completa.
        Retorna lista de SweepEvent validados.
        """
        sweeps = []
        
        for zone in zones:
            # Filtrar zona por dirección
            if macro_direction == Direction.LONG and not zone.is_low:
                continue
            if macro_direction == Direction.SHORT and not zone.is_high:
                continue
            
            sweep = self.detect_sweep_5m(candles_5m, zone, macro_direction)
            if sweep:
                # Enriquecer con ATR y validar
                sweep_idx = sweep.sweep_index
                if sweep_idx < len(atr_values):
                    sweep.atr_value = float(atr_values.iloc[sweep_idx])
                
                # Validar volumen spike
                sweep_candle = candles_5m.iloc[sweep_idx]
                recent_vol = candles_5m["tick_volume"].iloc[max(0, sweep_idx-20):sweep_idx]
                avg_vol = recent_vol.mean() if len(recent_vol) > 0 else 1
                sweep.volume_spike = sweep_candle["tick_volume"] >= avg_vol * volume_threshold
                
                sweeps.append(sweep)
        
        return sweeps


def calculate_atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcula ATR (Average True Range) usando método Wilder.
    Retorna Series alineada con candles.
    """
    high = candles["high"]
    low = candles["low"]
    close = candles["close"].shift(1)
    
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Wilder's smoothing (EMA con alpha = 1/period)
    atr = true_range.ewm(alpha=1/period, adjust=False).mean()
    
    return atr