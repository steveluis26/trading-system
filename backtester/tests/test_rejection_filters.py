"""
Tests for Rejection Filters - Las 3 condiciones mecánicas exactas
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
from backtester.config_loader import get_risk, get_instruments


class TestRejectionFilters:
    """Tests para las 3 condiciones mecánicas de validación de rechazo."""

    @pytest.fixture
    def engine(self):
        return TriggerEngine()

    @pytest.fixture
    def base_sweep(self):
        """Sweep base válido para tests."""
        return SweepEvent(
            sweep_candle={
                "high": 2010.0, "low": 2000.0,
                "open": 2008.0, "close": 2006.0,
                "tick_volume": 500
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
            penetration_pips=5.0,  # 2005 - 2000 = 5 pips (XAUUSD)
            wick_ratio=0.6,  # 60% - válido
            candles_to_reclaim=1,
            volume_spike=True,
            atr_value=8.0,  # ATR = 8 pips
        )

    @pytest.fixture
    def candles_5m(self):
        """DataFrame 5M sintético para validación."""
        mexico_tz = zoneinfo.ZoneInfo("America/Mexico_City")
        base = datetime(2024, 1, 15, 10, 0, tzinfo=mexico_tz)

        data = []
        for i in range(20):
            ts = base + timedelta(minutes=5*i)
            data.append({
                "timestamp": ts,
                "open": 2005.0, "high": 2012.0, "low": 2000.0, "close": 2008.0,
                "tick_volume": 400
            })
        return pd.DataFrame(data)

    # ============================================================
    # CONDICIÓN 1: Profundidad Máxima (ATR Filter) - ≤ 1 ATR
    # ============================================================

    def test_atr_filter_pass_penetration_less_than_atr(self, engine, base_sweep, candles_5m):
        """Penetración 5 pips < ATR 8 pips → PASS"""
        sweep = base_sweep.model_copy()
        sweep.penetration_pips = 5.0
        sweep.atr_value = 8.0

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True
        assert "Rechazo válido" in reason

    def test_atr_filter_pass_penetration_equals_atr(self, engine, base_sweep, candles_5m):
        """Penetración = 1 ATR exactamente → PASS (límite inclusivo)"""
        sweep = base_sweep.model_copy()
        sweep.penetration_pips = 8.0
        sweep.atr_value = 8.0

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_atr_filter_fail_penetration_greater_than_atr(self, engine, base_sweep, candles_5m):
        """Penetración 10 pips > ATR 8 pips → FAIL (rompimiento real)"""
        sweep = base_sweep.model_copy()
        sweep.penetration_pips = 10.0
        sweep.atr_value = 8.0

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "rompimiento real" in reason
        assert "10.0" in reason

    # ============================================================
    # CONDICIÓN 2: Anatomía de la Vela - Mecha ≥ 50% FIJO
    # ============================================================

    def test_wick_ratio_pass_exactly_50pct(self, engine, base_sweep, candles_5m):
        """Mecha exactamente 50% → PASS (FIJO, no rango)"""
        sweep = base_sweep.model_copy()
        # LONG: mecha inferior = min(open,close) - low = 2005 - 2000 = 5
        # rango = 10, ratio = 5/10 = 0.5 → PASS
        sweep.sweep_candle = {"high": 2010.0, "low": 2000.0, "open": 2005.0, "close": 2005.0}

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_wick_ratio_pass_60pct(self, engine, base_sweep, candles_5m):
        """Mecha 60% → PASS"""
        sweep = base_sweep.model_copy()
        # mecha = 6, rango = 10
        sweep.sweep_candle = {"high": 2010.0, "low": 2000.0, "open": 2006.0, "close": 2006.0}

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_wick_ratio_fail_40pct(self, engine, base_sweep, candles_5m):
        """Mecha 40% → FAIL (50% FIJO, no 40-50%)"""
        sweep = base_sweep.model_copy()
        # Mecha = 40% del rango: rango=10, mecha=4
        # LONG: lower_wick = min(open,close) - low = 4
        # low=2000, min(open,close)=2004 → open=2004, close=2004
        sweep.sweep_candle = {"high": 2010.0, "low": 2000.0, "open": 2004.0, "close": 2004.0}

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "50%" in reason

    def test_wick_ratio_fail_49pct(self, engine, base_sweep, candles_5m):
        """Mecha 49% → FAIL (debe ser ≥50% FIJO)"""
        sweep = base_sweep.model_copy()
        # Mecha 4.9 en rango 10 = 49%
        sweep.sweep_candle = {"high": 2010.0, "low": 2000.0, "open": 2004.9, "close": 2004.9}

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "50%" in reason

    def test_wick_ratio_short_direction(self, engine, base_sweep, candles_5m):
        """SHORT: mecha superior ≥ 50%"""
        sweep = base_sweep.model_copy()
        sweep.direction = Direction.SHORT
        sweep.level = 2015.0
        sweep.penetration_pips = 5.0
        # SHORT: mecha superior = high - max(open, close)
        # high=2020, max(open,close)=2014, mecha=6, rango=10, ratio=0.6
        sweep.sweep_candle = {"high": 2020.0, "low": 2010.0, "open": 2012.0, "close": 2014.0}

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    # ============================================================
    # CONDICIÓN 3: Factor Tiempo - Reclaim ≤ 2 VELAS MÁXIMO
    # ============================================================

    def test_time_reclaim_pass_1_candle(self, engine, base_sweep, candles_5m):
        """Reclaim en 1 vela → PASS"""
        sweep = base_sweep.model_copy()
        sweep.candles_to_reclaim = 1

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_time_reclaim_pass_2_candles(self, engine, base_sweep, candles_5m):
        """Reclaim en 2 velas → PASS (máximo permitido)"""
        sweep = base_sweep.model_copy()
        sweep.candles_to_reclaim = 2

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_time_reclaim_fail_3_candles(self, engine, base_sweep, candles_5m):
        """Reclaim en 3 velas → FAIL (máx 2, no 3)"""
        sweep = base_sweep.model_copy()
        sweep.candles_to_reclaim = 3

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "momentum perdido" in reason or "aceptación precio" in reason
        assert "2" in reason

    def test_time_reclaim_fail_4_candles(self, engine, base_sweep, candles_5m):
        """Reclaim en 4 velas → FAIL"""
        sweep = base_sweep.model_copy()
        sweep.candles_to_reclaim = 4

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False

    # ============================================================
    # RECLAIM BODY CLOSE CHECK (validación adicional)
    # ============================================================

    def test_reclaim_body_close_long_pass(self, engine, base_sweep, candles_5m):
        """LONG: reclaim cierra CUERPO arriba del nivel → PASS"""
        sweep = base_sweep.model_copy()
        sweep.direction = Direction.LONG
        sweep.level = 2005.0
        sweep.reclaim_candle = {"close": 2009.0}  # Cierra arriba

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_reclaim_body_close_long_fail(self, engine, base_sweep, candles_5m):
        """LONG: reclaim cierra CUERPO abajo/igual del nivel → FAIL"""
        sweep = base_sweep.model_copy()
        sweep.direction = Direction.LONG
        sweep.level = 2005.0
        sweep.reclaim_candle = {"close": 2005.0}  # Cierra EN el nivel (no cuerpo arriba)

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "cierra cuerpo arriba" in reason

    def test_reclaim_body_close_short_pass(self, engine, base_sweep, candles_5m):
        """SHORT: reclaim cierra CUERPO abajo del nivel → PASS"""
        sweep = base_sweep.model_copy()
        sweep.direction = Direction.SHORT
        sweep.level = 2015.0
        # SHORT necesita mecha superior ≥50%: high=2020, max(open,close)=2014, mecha=6, rango=10, ratio=0.6
        sweep.sweep_candle = {"high": 2020.0, "low": 2010.0, "open": 2012.0, "close": 2014.0, "tick_volume": 500}
        sweep.reclaim_candle = {"close": 2012.0}  # Cierra abajo
        sweep.penetration_pips = 5.0
        sweep.atr_value = 8.0

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is True

    def test_reclaim_body_close_short_fail(self, engine, base_sweep, candles_5m):
        """SHORT: reclaim cierra CUERPO arriba/igual del nivel → FAIL"""
        sweep = base_sweep.model_copy()
        sweep.direction = Direction.SHORT
        sweep.level = 2015.0
        # Mecha válida para pasar filtro 2
        sweep.sweep_candle = {"high": 2020.0, "low": 2010.0, "open": 2012.0, "close": 2014.0, "tick_volume": 500}
        sweep.reclaim_candle = {"close": 2015.0}  # Cierra EN el nivel
        sweep.penetration_pips = 5.0
        sweep.atr_value = 8.0

        valid, reason = engine.validate_rejection(sweep, candles_5m)
        assert valid is False
        assert "cierra cuerpo abajo" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])