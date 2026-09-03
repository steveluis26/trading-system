"""
Backtest Runner - Orquesta walk-forward backtest completo con métricas
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import json
from pathlib import Path
from backtester.config_loader import get_risk, get_instruments, get_sessions
from backtester.data_loader import DataLoader, load_backtest_data
from backtester.session_calculator import SessionCalculator, calculate_session_levels_for_backtest
from backtester.structure_analyzer import StructureAnalyzer, analyze_structure_for_backtest
from backtester.setup_detector import SetupDetector, calculate_atr
from backtester.trigger_engine import TriggerEngine, run_trigger_engine_for_backtest
from backtester.position_simulator import PositionSimulator, simulate_position_lifecycle
from backtester.risk_engine import RiskEngine, create_risk_engine
from backtester.models import (
    BacktestResult, BacktestMetrics, ClosedTrade, AccountState, SignalType, Direction
)


class BacktestRunner:
    """
    Orquesta backtest walk-forward completo:
    1. Carga datos multi-timeframe
    2. Calcula niveles sesión diarios
    3. Analiza estructura macro (1D)
    4. Detecta setups (confluencia + sweep 15M/5M)
    5. Valida triggers (3 filtros + double cross + volumen)
    6. Simula posiciones con risk engine
    7. Genera métricas y equity curve
    """
    
    def __init__(
        self,
        symbols: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        initial_balance: float = 10000.0,
        data_dir: str = "data/raw",
        output_dir: str = "backtester/results"
    ):
        self.symbols = symbols or ["XAUUSD", "EURUSD", "GBPUSD"]
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.data_dir = data_dir
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Configs
        self.risk_config = get_risk()
        self.instruments = get_instruments()
        self.sessions = get_sessions()
        
        # Components
        self.data_loader = DataLoader(data_dir)
        self.session_calc = SessionCalculator(self.sessions)
        self.structure_analyzer = StructureAnalyzer(self.risk_config)
        self.setup_detector = SetupDetector(self.risk_config, self.instruments)
        self.trigger_engine = TriggerEngine(self.risk_config, self.instruments)
        self.position_sim = PositionSimulator(self.risk_config, self.instruments)
        self.risk_engine = create_risk_engine(initial_balance)
        
        # State
        self.all_trades: List[ClosedTrade] = []
        self.equity_curve: List[Dict] = []
        self.current_balance = initial_balance
        self.signals_generated = 0
        self.signals_rejected_risk = 0
        self.setup_detections = 0
        self.rejection_validations_passed = 0
        self.rejection_validations_total = 0
    
    def run(self) -> BacktestResult:
        """Ejecuta backtest completo walk-forward."""
        print(f"🚀 Iniciando backtest: {self.symbols} | {self.start_date} → {self.end_date}")
        print(f"💰 Balance inicial: ${self.initial_balance:,.2f}")
        
        # 1. Cargar datos
        print("\n📊 Cargando datos históricos...")
        data = self.data_loader.load_multiple_symbols(
            self.symbols,
            start_date=self.start_date,
            end_date=self.end_date
        )
        
        # 2. Procesar cada símbolo
        for symbol in self.symbols:
            print(f"\n🔄 Procesando {symbol}...")
            self._run_symbol_backtest(symbol, data[symbol])
        
        # 3. Calcular métricas finales
        print("\n📈 Calculando métricas finales...")
        metrics = self._calculate_metrics()
        
        # 4. Guardar resultados
        result = BacktestResult(
            trades=self.all_trades,
            equity_curve=self.equity_curve,
            metrics=metrics,
            config_snapshot=self._get_config_snapshot(),
            start_date=pd.Timestamp(self.start_date) if self.start_date else datetime.now(),
            end_date=pd.Timestamp(self.end_date) if self.end_date else datetime.now(),
            initial_balance=self.initial_balance,
            final_balance=self.current_balance
        )
        
        self._save_results(result)
        
        # Print summary
        self._print_summary(metrics)
        
        return result
    
    def _run_symbol_backtest(self, symbol: str, symbol_data: Dict):
        """Backtest walk-forward para un símbolo."""
        candles_5m = symbol_data["5M"]
        candles_15m = symbol_data["15M"]
        candles_1h = symbol_data["1H"]
        candles_4h = symbol_data["4H"]
        candles_1d = symbol_data["1D"]
        
        if len(candles_5m) < 100:
            print(f"  ⚠️  Datos insuficientes para {symbol} ({len(candles_5m)} velas 5M)")
            return
        
        # Calcular ATR en 5M para validaciones
        atr_5m = calculate_atr(candles_5m, self.risk_config.rejection_validation.atr_period)
        
        # Calcular niveles de sesión para todo el rango
        print(f"  📅 Calculando niveles de sesión...")
        start_dt = pd.Timestamp(self.start_date) if self.start_date else candles_5m["timestamp"].iloc[0]
        end_dt = pd.Timestamp(self.end_date) if self.end_date else candles_5m["timestamp"].iloc[-1]
        
        daily_levels = calculate_session_levels_for_backtest(
            candles_5m, 
            start_dt.strftime("%Y-%m-%d"),
            end_dt.strftime("%Y-%m-%d"),
            symbol
        )
        
        # Walk-forward día por día
        dates = sorted(daily_levels.keys())
        print(f"  📆 {len(dates)} días de trading")
        
        for i, current_date in enumerate(dates):
            # Reset diario risk engine
            self.risk_engine.reset_daily()
            self.risk_engine.reset_monthly()
            
            # Obtener niveles del día
            session_levels, confluence_zones = daily_levels[current_date]
            if not confluence_zones:
                continue
            
            # Analizar estructura macro (1D) usando días previos
            # daily_levels contiene Tuple[SessionLevels, List[ConfluenceZone]], extraer solo SessionLevels
            daily_levels_only = {date: levels_zones[0] for date, levels_zones in daily_levels.items()}
            macro_structure = analyze_structure_for_backtest(
                daily_levels_only, candles_4h, current_date
            )
            
            if macro_structure.trend == "NEUTRAL":
                continue
            
            # Encontrar zona setup
            current_price = candles_5m["close"].iloc[i * 288] if i * 288 < len(candles_5m) else candles_5m["close"].iloc[-1]
            setup_zone = self.setup_detector.find_setup_zone(
                confluence_zones, macro_structure.trend.value, current_price
            )
            
            if not setup_zone:
                continue
            
            self.setup_detections += 1
            
            # Detectar sweeps en 5M para la zona
            # Filtrar velas 5M del día actual
            day_start = pd.Timestamp.combine(current_date, datetime.min.time()).tz_localize(self.sessions.timezone)
            day_end = day_start + timedelta(days=1)
            day_candles = candles_5m[
                (candles_5m["timestamp"] >= day_start) & 
                (candles_5m["timestamp"] < day_end)
            ].reset_index(drop=True)
            
            if len(day_candles) < 20:
                continue
            
            # ATR alineado
            day_atr = calculate_atr(day_candles, self.risk_config.rejection_validation.atr_period)
            
            sweeps = self.setup_detector.scan_for_sweeps(
                day_candles, [setup_zone], 
                Direction.LONG if macro_structure.trend == "BULLISH" else Direction.SHORT,
                day_atr
            )
            
            if not sweeps:
                continue
            
            # Trigger engine
            signals = run_trigger_engine_for_backtest(
                sweeps, day_candles, symbol,
                session_levels, macro_structure, confluence_zones,
                self.risk_config.risk_reward.ratio
            )
            
            for signal in signals:
                self.signals_generated += 1
                
                # Risk engine validation
                verdict = self.risk_engine.validate_pre_trade(signal)
                
                if not verdict.allow:
                    self.signals_rejected_risk += 1
                    continue
                
                # Simular posición
                trade, equity_df = simulate_position_lifecycle(
                    signal, day_candles, self.current_balance,
                    self.risk_config, self.instruments
                )
                
                self.all_trades.append(trade)
                self.current_balance += trade.pnl_usd
                
                # Actualizar equity curve
                for _, row in equity_df.iterrows():
                    self.equity_curve.append({
                        "timestamp": row["timestamp"],
                        "equity": row["equity"],
                        "symbol": symbol,
                        "trade_id": row["trade_id"]
                    })
                
                # Actualizar risk engine
                self.risk_engine.on_trade_closed(trade.pnl_usd, trade.exit_reason)
        
        print(f"  ✅ {symbol}: {len([t for t in self.all_trades if t.position.symbol == symbol])} trades")
    
    def _calculate_metrics(self) -> BacktestMetrics:
        """Calcula métricas finales del backtest."""
        if not self.all_trades:
            return BacktestMetrics()
        
        trades = self.all_trades
        winning = [t for t in trades if t.pnl_usd > 0]
        losing = [t for t in trades if t.pnl_usd <= 0]
        
        total = len(trades)
        wins = len(winning)
        losses = len(losing)
        win_rate = wins / total if total > 0 else 0
        
        gross_profit = sum(t.pnl_usd for t in winning)
        gross_loss = abs(sum(t.pnl_usd for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        net_profit = sum(t.pnl_usd for t in trades)
        net_profit_pct = net_profit / self.initial_balance * 100
        
        # Max drawdown
        equity_vals = [e["equity"] for e in self.equity_curve]
        peak = self.initial_balance
        max_dd = 0.0
        max_dd_usd = 0.0
        for eq in equity_vals:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            dd_usd = peak - eq
            if dd > max_dd:
                max_dd = dd
                max_dd_usd = dd_usd
        
        # Sharpe (simplificado, daily returns)
        if len(equity_vals) > 1:
            returns = np.diff(equity_vals) / equity_vals[:-1]
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0
        
        avg_win = np.mean([t.pnl_usd for t in winning]) if winning else 0
        avg_loss = np.mean([t.pnl_usd for t in losing]) if losing else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        
        # Consecutive
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0
        
        for t in trades:
            if t.pnl_usd > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)
        
        # Rejection validation stats
        rej_pass_rate = self.rejection_validations_passed / self.rejection_validations_total if self.rejection_validations_total > 0 else 0
        
        return BacktestMetrics(
            total_trades=total,
            winning_trades=wins,
            losing_trades=losses,
            win_rate=win_rate,
            profit_factor=profit_factor if profit_factor != float('inf') else 999.0,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
            max_drawdown_pct=max_dd,
            max_drawdown_usd=max_dd_usd,
            sharpe_ratio=sharpe,
            expectancy=expectancy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            risk_engine_blocks=self.signals_rejected_risk,
            setup_detection_rate=self.setup_detections / max(1, len(set(t.position.signal.timestamp.date() for t in trades))),
            rejection_validation_pass_rate=rej_pass_rate,
            avg_trade_duration_minutes=np.mean([t.duration_minutes for t in trades]) if trades else 0
        )
    
    def _get_config_snapshot(self) -> Dict:
        """Snapshot de config usada para reproducibilidad."""
        return {
            "risk": self.risk_config.model_dump(),
            "instruments": {k: v.model_dump() for k, v in self.instruments.instruments.items()},
            "sessions": self.sessions.model_dump(),
            "initial_balance": self.initial_balance,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date
        }
    
    def _save_results(self, result: BacktestResult):
        """Guarda resultados en JSON y CSV."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON completo
        json_path = self.output_dir / f"backtest_{timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2, default=str)
        
        # CSV trades
        if result.trades:
            trades_df = pd.DataFrame([{
                "trade_id": t.position.id,
                "symbol": t.position.symbol,
                "direction": t.position.direction.value,
                "entry_time": t.position.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.position.entry_price,
                "exit_price": t.exit_price,
                "sl_price": t.position.current_sl,
                "tp_price": t.position.current_tp,
                "lot_size": t.position.lot_size,
                "pnl_usd": t.pnl_usd,
                "pnl_pips": t.pnl_pips,
                "exit_reason": t.exit_reason.value,
                "duration_minutes": t.duration_minutes,
                "breakeven_hit": t.breakeven_hit,
                "partials_taken": len(t.partials_taken)
            } for t in result.trades])
            
            csv_path = self.output_dir / f"trades_{timestamp}.csv"
            trades_df.to_csv(csv_path, index=False)
            print(f"💾 Resultados guardados: {json_path}, {csv_path}")
        else:
            print(f"💾 Resultados guardados: {json_path}")
    
    def _print_summary(self, metrics: BacktestMetrics):
        """Imprime resumen final."""
        print("\n" + "="*60)
        print("📊 BACKTEST SUMMARY")
        print("="*60)
        print(f"💰 Balance inicial:    ${self.initial_balance:,.2f}")
        print(f"💰 Balance final:      ${self.current_balance:,.2f}")
        print(f"📈 Net Profit:         ${metrics.net_profit:,.2f} ({metrics.net_profit_pct:+.2f}%)")
        print(f"📊 Total Trades:       {metrics.total_trades}")
        print(f"✅ Winning:            {metrics.winning_trades}")
        print(f"❌ Losing:             {metrics.losing_trades}")
        print(f"🎯 Win Rate:           {metrics.win_rate*100:.1f}%")
        print(f"⚖️  Profit Factor:      {metrics.profit_factor:.2f}")
        print(f"📉 Max Drawdown:       {metrics.max_drawdown_pct:.2f}% (${metrics.max_drawdown_usd:,.2f})")
        print(f"📐 Sharpe Ratio:       {metrics.sharpe_ratio:.2f}")
        print(f"🎲 Expectancy:         ${metrics.expectancy:.2f}/trade")
        print(f"📊 Avg Win:            ${metrics.avg_win:.2f}")
        print(f"📊 Avg Loss:           ${metrics.avg_loss:.2f}")
        print(f"🔥 Max Consec Wins:    {metrics.max_consecutive_wins}")
        print(f"🧊 Max Consec Losses:  {metrics.max_consecutive_losses}")
        print(f"🛡️  Risk Blocks:       {metrics.risk_engine_blocks}")
        print(f"🔍 Setup Detections:   {self.setup_detections}")
        print(f"✅ Rejection Pass Rate: {metrics.rejection_validation_pass_rate*100:.1f}%")
        print(f"⏱️  Avg Duration:       {metrics.avg_trade_duration_minutes:.0f} min")
        print("="*60)


def run_backtest(
    symbols: List[str] = None,
    start_date: str = "2024-01-01",
    end_date: str = "2024-12-31",
    initial_balance: float = 10000.0,
    data_dir: str = "data/raw"
) -> BacktestResult:
    """Función de conveniencia para correr backtest."""
    runner = BacktestRunner(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance,
        data_dir=data_dir
    )
    return runner.run()