"""
Structure Analyzer - Análisis de estructura de mercado macro (1D/4H/1H)
Detecta HH/HL/LH/LL, tendencia, BOS/CHoCH usando niveles de sesión como pivotes.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from backtester.models import MarketStructure, Trend, Direction, SessionLevels
from backtester.config_loader import get_risk


class StructureAnalyzer:
    """
    Analiza estructura de mercado usando High/Low de sesiones como pivotes objetivos.
    No usa conteo de velas arbitrario — pivotes = niveles de sesión confirmados.
    """
    
    def __init__(self, risk_config=None):
        self.config = risk_config or get_risk()
        self.lookback_days = self.config.structure.trend_lookback_days
        self.min_pivots = self.config.structure.min_pivots_for_trend
    
    def analyze_daily_structure(
        self, 
        daily_levels: Dict[datetime, SessionLevels],
        current_date: datetime
    ) -> MarketStructure:
        """
        Analiza tendencia en 1D usando últimos N días de niveles de sesión.
        
        Args:
            daily_levels: {date: SessionLevels} del backtest
            current_date: Fecha actual del análisis
            
        Returns:
            MarketStructure con trend, pivotes, último BOS/CHoCH
        """
        # Obtener últimos N días disponibles antes de current_date
        past_dates = sorted([d for d in daily_levels.keys() if d < current_date])[-self.lookback_days:]
        
        if len(past_dates) < self.min_pivots:
            return MarketStructure(
                trend=Trend.NEUTRAL,
                pivots=[],
                timeframe="1D",
                timestamp=current_date
            )
        
        # Extraer Highs y Lows de London (sesión principal para estructura)
        highs = []
        lows = []
        pivot_dates = []
        
        for date in past_dates:
            levels = daily_levels[date]
            if levels.london.high is not None and levels.london.low is not None:
                highs.append(levels.london.high)
                lows.append(levels.london.low)
                pivot_dates.append(date)
        
        if len(highs) < self.min_pivots or len(lows) < self.min_pivots:
            return MarketStructure(
                trend=Trend.NEUTRAL,
                pivots=[],
                timeframe="1D",
                timestamp=current_date
            )
        
        # Detectar HH/HL/LH/LL en los últimos 3-4 pivotes
        recent_highs = highs[-4:]
        recent_lows = lows[-4:]
        recent_dates = pivot_dates[-4:]
        
        # Construir lista de pivotes para retorno
        pivots = []
        for i, (d, h, l) in enumerate(zip(recent_dates, recent_highs, recent_lows)):
            pivots.append({
                "date": d.isoformat(),
                "high": h,
                "low": l,
                "index": len(highs) - len(recent_highs) + i
            })
        
        # Clasificar tendencia
        trend = self._classify_trend(recent_highs, recent_lows)
        
        # Detectar último BOS/CHoCH
        last_bos = self._detect_last_bos_choch(recent_highs, recent_lows, recent_dates, trend)
        
        # Nivel clave para confirmación 4H/1H
        key_level = self._get_key_level(recent_highs, recent_lows, trend)
        
        return MarketStructure(
            trend=trend,
            last_bos=last_bos,
            pivots=pivots,
            key_level=key_level,
            timeframe="1D",
            timestamp=current_date
        )
    
    def _classify_trend(self, highs: List[float], lows: List[float]) -> Trend:
        """Clasifica tendencia basada en HH/HL vs LH/LL."""
        if len(highs) < 3 or len(lows) < 3:
            return Trend.NEUTRAL
        
        # Últimos 3 pivotes
        h1, h2, h3 = highs[-3], highs[-2], highs[-1]
        l1, l2, l3 = lows[-3], lows[-2], lows[-1]
        
        # HH = cada high > anterior; HL = cada low > anterior
        higher_highs = (h1 < h2 < h3)
        higher_lows = (l1 < l2 < l3)
        lower_highs = (h1 > h2 > h3)
        lower_lows = (l1 > l2 > l3)
        
        if higher_highs and higher_lows:
            return Trend.BULLISH
        elif lower_highs and lower_lows:
            return Trend.BEARISH
        else:
            return Trend.RANGING
    
    def _detect_last_bos_choch(
        self, 
        highs: List[float], 
        lows: List[float], 
        dates: List[datetime],
        current_trend: Trend
    ) -> Optional[Dict]:
        """Detecta último Break of Structure / Change of Character."""
        if len(highs) < 2 or len(lows) < 2:
            return None
        
        # BOS alcista: rompe high previo en tendencia bajista (CHoCH) o confirma alcista
        # BOS bajista: rompe low previo en tendencia alcista (CHoCH) o confirma bajista
        
        if current_trend == Trend.BULLISH:
            # Confirmación: high actual > high previo
            if highs[-1] > highs[-2]:
                return {
                    "type": "BOS_BULLISH",
                    "date": dates[-1].isoformat(),
                    "broken_level": highs[-2],
                    "break_price": highs[-1],
                    "direction": "UP"
                }
        elif current_trend == Trend.BEARISH:
            # Confirmación: low actual < low previo
            if lows[-1] < lows[-2]:
                return {
                    "type": "BOS_BEARISH",
                    "date": dates[-1].isoformat(),
                    "broken_level": lows[-2],
                    "break_price": lows[-1],
                    "direction": "DOWN"
                }
        elif current_trend == Trend.RANGING:
            # Posible CHoCH: rompimiento de rango
            recent_high = max(highs[-3:])
            recent_low = min(lows[-3:])
            if highs[-1] > recent_high:
                return {
                    "type": "CHOCH_BULLISH",
                    "date": dates[-1].isoformat(),
                    "broken_level": recent_high,
                    "break_price": highs[-1],
                    "direction": "UP"
                }
            elif lows[-1] < recent_low:
                return {
                    "type": "CHOCH_BEARISH",
                    "date": dates[-1].isoformat(),
                    "broken_level": recent_low,
                    "break_price": lows[-1],
                    "direction": "DOWN"
                }
        
        return None
    
    def _get_key_level(self, highs: List[float], lows: List[float], trend: Trend) -> Optional[float]:
        """Nivel clave para confirmación en timeframes menores."""
        if trend == Trend.BULLISH:
            return min(lows[-3:])  # Low más reciente relevante (soporte)
        elif trend == Trend.BEARISH:
            return max(highs[-3:])  # High más reciente relevante (resistencia)
        return None
    
    def confirm_in_lower_tf(
        self,
        candles_4h: pd.DataFrame,
        macro_trend: Trend,
        key_level: float,
        lookback_candles: int = 50
    ) -> Optional[Dict]:
        """
        Busca confirmación BOS/CHoCH en 4H/1H.
        El precio debe romper y CERRAR claramente el nivel clave.
        """
        if key_level is None or len(candles_4h) < 10:
            return None
        
        recent = candles_4h.tail(lookback_candles)
        
        for idx, row in recent.iterrows():
            if macro_trend == Trend.BULLISH:
                # Buscar cierre arriba de key_level (resistencia rota = continuación)
                # O pullback a key_level con rechazo (soporte)
                if row["close"] > key_level and row["open"] < key_level:
                    return {
                        "type": "BOS_BULLISH_CONFIRM",
                        "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                        "level": key_level,
                        "close": row["close"],
                        "candle": row.to_dict()
                    }
            elif macro_trend == Trend.BEARISH:
                if row["close"] < key_level and row["open"] > key_level:
                    return {
                        "type": "BOS_BEARISH_CONFIRM",
                        "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                        "level": key_level,
                        "close": row["close"],
                        "candle": row.to_dict()
                    }
        
        return None


def analyze_structure_for_backtest(
    daily_levels: Dict[datetime, SessionLevels],
    candles_4h: pd.DataFrame,
    current_date: datetime
) -> MarketStructure:
    """Función de conveniencia para análisis completo en backtest."""
    analyzer = StructureAnalyzer()
    structure = analyzer.analyze_daily_structure(daily_levels, current_date)
    
    if structure.trend != Trend.NEUTRAL and structure.key_level is not None:
        confirm = analyzer.confirm_in_lower_tf(candles_4h, structure.trend, structure.key_level)
        if confirm:
            structure.last_bos = confirm
    
    return structure