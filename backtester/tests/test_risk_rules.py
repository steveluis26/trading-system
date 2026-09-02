"""
Tests for Position Sizing (1% riesgo dinámico) and Risk Rules
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtester.position_simulator import PositionSimulator
from backtester.risk_engine import RiskEngine, create_risk_engine
from backtester.models import AccountState, TradingSignal, SignalType, Direction
from backtester.config_loader import get_risk, get_instruments


class TestPositionSizing:
    """Tests para cálculo de lote dinámico 1% riesgo."""
    
    @pytest.fixture
    def sim(self):
        return PositionSimulator()
    
    def test_lot_size_xauusd_1pct_risk(self, sim):
        """XAUUSD: 1% riesgo, SL 45 pips → lote calculado."""
        balance = 10000.0
        sl_pips = 45
        symbol = "XAUUSD"
        
        lot = sim.calculate_lot_size(balance, sl_pips, symbol)
        
        # XAUUSD: 0.01 lot = $1/pip, 1 lot = $100/pip
        # risk = 10000 * 0.01 = $100
        # lot = 100 / (45 * 100) = 100 / 4500 = 0.0222... → redondeado a step 0.01
        assert lot >= 0.01
        assert lot % 0.01 == 0  # step = 0.01
    
    def test_lot_size_eurusd_1pct_risk(self, sim):
        """EURUSD: 1% riesgo, SL 30 pips."""
        balance = 10000.0
        sl_pips = 30
        symbol = "EURUSD"
        
        lot = sim.calculate_lot_size(balance, sl_pips, symbol)
        
        # EURUSD: 0.01 lot = $0.10/pip, 1 lot = $10/pip
        # risk = $100, lot = 100 / (30 * 10) = 0.333... → step 0.01
        assert lot >= 0.01
        assert abs(lot % 0.01) < 1e-10  # step = 0.01 (floating point tolerance)
    
    def test_lot_size_respects_min_max(self, sim):
        """Lote respeta min/max del instrumento."""
        # Balance muy pequeño → lote mínimo
        lot = sim.calculate_lot_size(100.0, 50, "XAUUSD")
        assert lot == 0.01  # min_lot
        
        # Balance muy grande → lote máximo
        lot = sim.calculate_lot_size(1000000.0, 10, "XAUUSD")
        assert lot <= 100.0  # max_lot
    
    def test_sl_tp_calculation_rr_1_2(self, sim):
        """SL/TP calculados con R:R 1:2 fijo."""
        entry = 2000.0
        sl_pips = 45
        symbol = "XAUUSD"
        
        sl, tp = sim.calculate_sl_tp_prices(entry, Direction.LONG, sl_pips, symbol)
        
        pip_size = 0.01  # XAUUSD
        expected_sl = entry - (sl_pips * pip_size)
        expected_tp = entry + (sl_pips * 2.0 * pip_size)  # 1:2
        
        assert sl == expected_sl
        assert tp == expected_tp
    
    def test_sl_tp_short_direction(self, sim):
        """SHORT: SL arriba, TP abajo."""
        entry = 2000.0
        sl_pips = 45
        symbol = "XAUUSD"
        
        sl, tp = sim.calculate_sl_tp_prices(entry, Direction.SHORT, sl_pips, symbol)
        
        pip_size = 0.01
        assert sl == entry + (sl_pips * pip_size)
        assert tp == entry - (sl_pips * 2.0 * pip_size)


class TestRiskRules:
    """Tests para reglas de riesgo inquebrantables."""
    
    @pytest.fixture
    def risk_engine(self):
        return create_risk_engine(10000.0)
    
    @pytest.fixture
    def valid_signal(self):
        """Señal válida completa."""
        return TradingSignal(
            signal_type=SignalType.ENTRY,
            direction=Direction.LONG,
            symbol="XAUUSD",
            entry_price=2000.0,
            sl_pips=45,
            tp_pips=90,
            sl_price=1995.5,
            tp_price=2009.0,
            lot_size=0.02,
            confidence=0.8,
            timestamp=datetime(2024, 1, 15, 10, 0),
            trigger_level=1995.0,
            validation_details={"double_cross": True, "volume_confirmed": True}
        )
    
    def test_allow_valid_signal(self, risk_engine, valid_signal):
        """Señal válida con cuenta sana → ALLOW."""
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is True
    
    def test_block_max_concurrent_trades(self, risk_engine, valid_signal):
        """Máx 2 posiciones concurrentes → BLOCK."""
        # Agregar 2 posiciones abiertas
        risk_engine.account.open_positions = [
            type('P', (), {'status': 'OPEN'})(),
            type('P', (), {'status': 'OPEN'})()
        ]
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert "concurrent" in verdict.reason.lower()
    
    def test_block_max_daily_trades(self, risk_engine, valid_signal):
        """Máx 5 trades/día → BLOCK."""
        risk_engine.account.daily_trades = 5
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert "diario" in verdict.reason.lower()
    
    def test_block_daily_loss_limit_5pct(self, risk_engine, valid_signal):
        """Pérdida diaria 5% → BLOCK y bloquea cuenta."""
        risk_engine.account.daily_pnl = -501.0  # -5.01%
        risk_engine.account.balance = 10000.0
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert risk_engine.account.is_blocked is True
        assert "diaria" in verdict.reason.lower()
    
    def test_block_monthly_loss_limit_30pct(self, risk_engine, valid_signal):
        """Pérdida mensual 30% → BLOCK y bloquea cuenta."""
        risk_engine.account.monthly_pnl = -3001.0  # -30.01%
        risk_engine.account.balance = 10000.0
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert risk_engine.account.is_blocked is True
        assert "mensual" in verdict.reason.lower()
    
    def test_block_5_consecutive_losses(self, risk_engine, valid_signal):
        """5 pérdidas consecutivas → BLOCK y bloquea cuenta."""
        risk_engine.account.consecutive_losses = 5
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert risk_engine.account.is_blocked is True
        assert "consecutiva" in verdict.reason.lower()
    
    def test_manual_reactivate_only_mariely(self, risk_engine):
        """Reactivación solo manual por Mariely."""
        risk_engine.account.is_blocked = True
        risk_engine.account.block_reason = "test"
        
        # Usuario no autorizado → error
        with pytest.raises(PermissionError):
            risk_engine.manual_reactivate("Otro")
        
        # Mariely → OK
        risk_engine.manual_reactivate("Mariely")
        assert risk_engine.account.is_blocked is False
        assert risk_engine.account.block_reason == ""
    
    def test_rr_minimum_validation(self, risk_engine, valid_signal):
        """R:R debe ser ≥ 1.9 (5% tolerancia del 2.0)."""
        valid_signal.sl_price = 1998.0  # SL 2 pips
        valid_signal.tp_price = 2000.5  # TP 0.5 pips → R:R 0.25
        
        verdict = risk_engine.validate_pre_trade(valid_signal)
        assert verdict.allow is False
        assert "R:R" in verdict.reason
    
    def test_on_trade_closed_updates_state(self, risk_engine, valid_signal):
        """Cierre de trade actualiza métricas correctamente."""
        initial_balance = risk_engine.account.balance
        pnl = -100.0  # Loss
        
        risk_engine.on_trade_closed(pnl, SignalType.EXIT_SL)
        
        assert risk_engine.account.balance == initial_balance + pnl
        assert risk_engine.account.daily_pnl == pnl
        assert risk_engine.account.monthly_pnl == pnl
        assert risk_engine.account.daily_trades == 1
        assert risk_engine.account.consecutive_losses == 1
    
    def test_on_trade_closed_win_resets_consecutive(self, risk_engine, valid_signal):
        """Trade ganador resetea pérdidas consecutivas."""
        risk_engine.account.consecutive_losses = 3
        
        risk_engine.on_trade_closed(100.0, SignalType.EXIT_TP)  # Win
        
        assert risk_engine.account.consecutive_losses == 0
    
    def test_incomplete_signal_rejected(self, risk_engine):
        """Señal incompleta → REJECT."""
        signal = TradingSignal(
            signal_type=SignalType.ENTRY,
            direction=Direction.LONG,
            symbol="XAUUSD",
            entry_price=2000.0,
            sl_pips=45,
            tp_pips=90,
            sl_price=0,  # Falta
            tp_price=0,  # Falta
            lot_size=0,
            confidence=0.8,
            timestamp=datetime(2024, 1, 15, 10, 0),
            trigger_level=1995.0
        )
        
        verdict = risk_engine.validate_pre_trade(signal)
        assert verdict.allow is False
        assert "incompleta" in verdict.reason.lower()


# Import datetime for tests
from datetime import datetime

if __name__ == "__main__":
    pytest.main([__file__, "-v"])