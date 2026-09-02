"""
Tests for Double Cross Entry Trigger
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import zoneinfo
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtester.trigger_engine import TriggerEngine
from backtester.models import SweepEvent, Direction
from backtester.config_loader import get_risk


class TestDoubleCross:
    """Tests para el gatillo de doble cruce."""
    
    @pytest.fixture
    def engine(self):
        return TriggerEngine()
    
    @pytest.fixture
    def validated_sweep(self):
        """Sweep que pasa todas las validaciones."""
        return SweepEvent(
            sweep_candle={
                "high": 2010.0, "low": 2000.0, 
                "open": 2008.0, "close": 2006.0,
                "tick_volume": 600
            },
            reclaim_candle={
                "high": 2012.0, "low": 2005.0,
                "open": 2007.0, "close": 2009.0,
                "tick_volume": 800
            },
            sweep_index=10,
            reclaim_index=11,
            level=2005.0,
            direction=Direction.LONG,
            penetration_pips=5.0,
            wick_ratio=0.6,
            candles_to_reclaim=1,
            volume_spike=True,
            atr_value=8.0,
            validation_passed=True,
            validation_reason="OK"
        )
    
    @pytest.fixture
    def candles_5m_with_next(self):
        """Velas 5M incluyendo la vela SIGUIENTE al reclaim (entrada)."""
        mexico_tz = zoneinfo.ZoneInfo("America/Mexico_City")
        base = datetime(2024, 1, 15, 10, 0, tzinfo=mexico_tz)
        
        data = []
        for i in range(15):
            ts = base + timedelta(minutes=5*i)
            data.append({
                "timestamp": ts,
                "open": 2008.0 + i*0.1,  # Precio subiendo
                "high": 2012.0 + i*0.1,
                "low": 2005.0 + i*0.1,
                "close": 2010.0 + i*0.1,
                "tick_volume": 400 + i*10
            })
        return pd.DataFrame(data)
    
    def test_double_cross_entry_generated(self, engine, validated_sweep, candles_5m_with_next):
        """Double cross válido → genera entrada MARKET en open de vela siguiente."""
        entry_data = engine.check_double_cross_entry(
            validated_sweep, candles_5m_with_next, True, True
        )
        
        assert entry_data is not None
        assert entry_data["signal_type"].value == "ENTRY"
        assert entry_data["direction"] == Direction.LONG
        # Entrada en OPEN de vela 12 (reclaim_index=11, entry_idx=12)
        assert entry_data["entry_price"] == candles_5m_with_next.iloc[12]["open"]
        assert entry_data["trigger_level"] == 2005.0
    
    def test_no_entry_if_rejection_failed(self, engine, validated_sweep, candles_5m_with_next):
        """Si validación falló → NO hay entrada."""
        entry_data = engine.check_double_cross_entry(
            validated_sweep, candles_5m_with_next, False, True
        )
        assert entry_data is None
    
    def test_no_entry_if_volume_failed(self, engine, validated_sweep, candles_5m_with_next):
        """Si volumen falló → NO hay entrada."""
        entry_data = engine.check_double_cross_entry(
            validated_sweep, candles_5m_with_next, True, False
        )
        assert entry_data is None
    
    def test_no_entry_if_no_next_candle(self, engine, validated_sweep, candles_5m_with_next):
        """Si no hay vela siguiente (fin de datos) → NO hay entrada."""
        # Solo 12 velas, reclaim_index=11, no hay vela 12
        short_candles = candles_5m_with_next.iloc[:12].copy()
        
        entry_data = engine.check_double_cross_entry(
            validated_sweep, short_candles, True, True
        )
        assert entry_data is None
    
    def test_short_double_cross(self, engine, validated_sweep, candles_5m_with_next):
        """SHORT: doble cruce hacia abajo."""
        sweep = validated_sweep.model_copy()
        sweep.direction = Direction.SHORT
        sweep.level = 2015.0
        sweep.reclaim_candle = {"close": 2012.0}  # Cierra abajo
        
        # Velas bajando
        candles = candles_5m_with_next.copy()
        candles["open"] = 2012.0 - candles.index * 0.1
        candles["high"] = 2014.0 - candles.index * 0.1
        candles["low"] = 2008.0 - candles.index * 0.1
        candles["close"] = 2010.0 - candles.index * 0.1
        
        entry_data = engine.check_double_cross_entry(
            sweep, candles, True, True
        )
        
        assert entry_data is not None
        assert entry_data["direction"] == Direction.SHORT
        assert entry_data["entry_price"] == candles.iloc[12]["open"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])