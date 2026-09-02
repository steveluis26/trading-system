"""
Tests for Session Calculator - Niveles de sesión y confluencia
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import zoneinfo
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtester.session_calculator import SessionCalculator
from backtester.models import SessionName, ConfluenceZone
from backtester.config_loader import get_sessions


class TestSessionCalculator:
    
    @pytest.fixture
    def sample_candles_5m(self):
        """Genera velas 5M sintéticas para un día completo."""
        mexico_tz = zoneinfo.ZoneInfo("America/Mexico_City")
        base_date = datetime(2024, 1, 15, tzinfo=mexico_tz)
        
        # Generar 288 velas (24h * 12 velas/hora = 288)
        timestamps = []
        candles = []
        
        base_price = 2000.0  # XAUUSD aprox
        for i in range(288):
            ts = base_date + timedelta(minutes=5*i)
            timestamps.append(ts)
            
            # Precio con algo de ruido
            noise = np.random.normal(0, 0.5)
            open_price = base_price + noise
            high_price = open_price + abs(np.random.normal(0, 1.0))
            low_price = open_price - abs(np.random.normal(0, 1.0))
            close_price = open_price + np.random.normal(0, 0.5)
            
            candles.append({
                "timestamp": ts,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "tick_volume": np.random.randint(100, 1000)
            })
        
        df = pd.DataFrame(candles)
        df.set_index("timestamp", inplace=True)
        return df
    
    def test_calculate_daily_levels(self, sample_candles_5m):
        calc = SessionCalculator()
        date = datetime(2024, 1, 15)
        
        levels = calc.calculate_daily_levels(sample_candles_5m, date)
        
        assert levels.date.date() == date.date()
        assert levels.asia.candle_count > 0
        assert levels.london.candle_count > 0
        assert levels.newyork.candle_count > 0
        assert levels.asia.high is not None
        assert levels.asia.low is not None
        assert levels.london.high is not None
        assert levels.london.low is not None
        assert levels.newyork.high is not None
        assert levels.newyork.low is not None
    
    def test_session_times_correct(self, sample_candles_5m):
        """Verifica que las sesiones tengan las horas correctas en zona México."""
        calc = SessionCalculator()
        date = datetime(2024, 1, 15)
        levels = calc.calculate_daily_levels(sample_candles_5m, date)
        
        # ASIA: 18:00 día anterior → 03:00 día actual
        assert levels.asia.start_time.hour == 18
        assert levels.asia.end_time.hour == 3
        
        # LONDON: 02:00 → 11:00
        assert levels.london.start_time.hour == 2
        assert levels.london.end_time.hour == 11
        
        # NEWYORK: 07:00 → 16:00
        assert levels.newyork.start_time.hour == 7
        assert levels.newyork.end_time.hour == 16
    
    def test_detect_confluence_zones(self, sample_candles_5m):
        calc = SessionCalculator()
        date = datetime(2024, 1, 15)
        levels = calc.calculate_daily_levels(sample_candles_5m, date)
        
        zones = calc.detect_confluence_zones(levels, "XAUUSD")
        
        # Debe detectar al menos algunas zonas (depende de datos aleatorios)
        # Con 100 pips tolerancia en XAUUSD (0.01 = $1/pip), hay buena probabilidad
        assert isinstance(zones, list)
        
        for zone in zones:
            assert zone.strength >= 2
            assert zone.tolerance_pips == 100  # XAUUSD = 100 pips
            assert isinstance(zone.is_high, bool)
            assert isinstance(zone.is_low, bool)
    
    def test_get_key_level_for_trend(self, sample_candles_5m):
        calc = SessionCalculator()
        date = datetime(2024, 1, 15)
        levels = calc.calculate_daily_levels(sample_candles_5m, date)
        
        # Bullish debe retornar un low
        key_bull = calc.get_key_level_for_trend(levels, "BULLISH")
        if key_bull:
            assert key_bull <= max(levels.london.high or 0, levels.newyork.high or 0)
        
        # Bearish debe retornar un high
        key_bear = calc.get_key_level_for_trend(levels, "BEARISH")
        if key_bear:
            assert key_bear >= min(levels.london.low or 99999, levels.newyork.low or 99999)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])