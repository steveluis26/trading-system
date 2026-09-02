"""
Tests for Config Loader
"""
import pytest
import tempfile
import yaml
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtester.config_loader import (
    get_instruments, get_sessions, get_risk, ConfigLoader
)


class TestConfigLoader:
    
    def test_load_risk_config(self):
        risk = get_risk()
        assert risk is not None
        assert risk.lot_sizing.mode == "pct_risk"
        assert risk.lot_sizing.risk_pct_per_trade == 0.01
        assert risk.risk_reward.ratio == 2.0
        assert risk.breakeven.trigger_pct_of_tp == 0.4
        assert risk.limits.daily_loss_limit_pct == 0.05
        assert risk.limits.monthly_loss_limit_pct == 0.30
        assert risk.limits.max_consecutive_losses == 5
    
    def test_load_sessions_config(self):
        sessions = get_sessions()
        assert sessions is not None
        assert sessions.timezone == "America/Mexico_City"
        assert "ASIA" in sessions.sessions
        assert "LONDON" in sessions.sessions
        assert "NEWYORK" in sessions.sessions
    
    def test_load_instruments_config(self):
        instruments = get_instruments()
        assert instruments is not None
        assert "XAUUSD" in instruments.instruments
        assert "EURUSD" in instruments.instruments
        assert "GBPUSD" in instruments.instruments
        
        xau = instruments.instruments["XAUUSD"]
        assert xau.pip_size == 0.01
        assert xau.pip_value_per_lot == 1.0
        assert xau.min_lot == 0.01
    
    def test_rejection_validation_config(self):
        risk = get_risk()
        val = risk.rejection_validation
        assert val.atr_period == 14
        assert val.max_penetration_atr == 1.0
        assert val.min_wick_ratio == 0.50  # 50% FIJO
        assert val.max_candles_to_reclaim == 2  # MÁX 2 VELAS
        assert val.require_volume_spike is True
        assert val.volume_spike_multiplier == 1.5
    
    def test_config_loader_class(self):
        """Test ConfigLoader class directly."""
        loader = ConfigLoader("config")
        inst, sess, risk = loader.load_all()
        assert inst is not None
        assert sess is not None
        assert risk is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])