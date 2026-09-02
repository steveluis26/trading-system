"""
Risk Engine - Motor de riesgo inquebrantable (validación pre-trade + kill-switches)
Es el guardián final: NINGUNA orden sale sin pasar por aquí.
"""
from datetime import datetime, date
from typing import Dict, List, Optional
from backtester.models import TradingSignal, AccountState, RiskVerdict, Direction, SignalType, Position
from backtester.config_loader import get_risk


class RiskEngine:
    """
    Validaciones inquebrantables pre-trade + monitoreo continuo de límites.
    
    Reglas (config/risk.yaml):
    - Max 2 posiciones concurrentes
    - Max 5 trades/día
    - Max 5% pérdida diaria → pausa día
    - Max 30% pérdida mensual → bloqueo total
    - Max 5 pérdidas consecutivas → bloqueo total
    - Reactivación SOLO manual
    - Filtro noticias (high impact USD)
    - Por cuenta individual (no agregado)
    """
    
    def __init__(self, risk_config=None, account: AccountState = None):
        self.config = risk_config or get_risk()
        self.account = account or AccountState(balance=10000.0, equity=10000.0)
        self.news_calendar = self._load_news_calendar()  # Placeholder
    
    def _load_news_calendar(self) -> Dict:
        """Carga calendario económico. Placeholder para integración real."""
        # TODO: Integrar con API calendario económico (ForexFactory, Investing.com, etc.)
        return {}
    
    def is_high_impact_news_day(self, check_date: date, currency: str = "USD") -> bool:
        """Verifica si hay noticias de alto impacto para la moneda en la fecha."""
        # Placeholder: en producción, consultar calendario real
        # Por ahora retorna False para no bloquear backtest
        return False
    
    def validate_pre_trade(self, signal: TradingSignal) -> RiskVerdict:
        """
        VALIDACIÓN COMPLETA PRE-TRADE.
        Se ejecuta ANTES de enviar cualquier orden.
        Retorna RiskVerdict(allow=True/False, reason, risk_metrics).
        """
        metrics = {}
        
        # 1. CUENTA BLOQUEADA
        if self.account.is_blocked:
            return RiskVerdict(
                allow=False,
                reason=f"Cuenta bloqueada: {self.account.block_reason}",
                risk_metrics={"blocked": True}
            )
        
        # 2. MÁXIMO POSICIONES CONCURRENTES
        open_count = len([p for p in self.account.open_positions if p.status == "OPEN"])
        max_concurrent = self.config.limits.max_concurrent_trades
        metrics["open_positions"] = open_count
        metrics["max_concurrent"] = max_concurrent
        
        if open_count >= max_concurrent:
            return RiskVerdict(
                allow=False,
                reason=f"Máx {max_concurrent} posiciones concurrentes (actual: {open_count})",
                risk_metrics=metrics
            )
        
        # 3. MÁXIMO TRADES DIARIOS
        max_daily = self.config.limits.max_daily_trades
        metrics["daily_trades"] = self.account.daily_trades
        metrics["max_daily"] = max_daily
        
        if self.account.daily_trades >= max_daily:
            return RiskVerdict(
                allow=False,
                reason=f"Máx {max_daily} trades diarios alcanzados",
                risk_metrics=metrics
            )
        
        # 4. LÍMITE PÉRDIDA DIARIA (5%)
        daily_loss_limit = self.config.limits.daily_loss_limit_pct
        daily_pnl_pct = self.account.daily_pnl / self.account.balance if self.account.balance > 0 else 0
        metrics["daily_pnl_pct"] = daily_pnl_pct
        metrics["daily_loss_limit_pct"] = daily_loss_limit
        
        if daily_pnl_pct <= -daily_loss_limit:
            self._block_account(f"Límite pérdida diaria {daily_loss_limit*100}% alcanzado")
            return RiskVerdict(
                allow=False,
                reason=f"Pérdida diaria {daily_pnl_pct*100:.1f}% ≥ límite {daily_loss_limit*100}%",
                risk_metrics=metrics
            )
        
        # 5. LÍMITE PÉRDIDA MENSUAL (30%)
        monthly_loss_limit = self.config.limits.monthly_loss_limit_pct
        monthly_pnl_pct = self.account.monthly_pnl / self.account.balance if self.account.balance > 0 else 0
        metrics["monthly_pnl_pct"] = monthly_pnl_pct
        metrics["monthly_loss_limit_pct"] = monthly_loss_limit
        
        if monthly_pnl_pct <= -monthly_loss_limit:
            self._block_account(f"Límite pérdida mensual {monthly_loss_limit*100}% alcanzado")
            return RiskVerdict(
                allow=False,
                reason=f"Pérdida mensual {monthly_pnl_pct*100:.1f}% ≥ límite {monthly_loss_limit*100}%",
                risk_metrics=metrics
            )
        
        # 6. MÁXIMO PÉRDIDAS CONSECUTIVAS (5)
        max_consecutive = self.config.limits.max_consecutive_losses
        metrics["consecutive_losses"] = self.account.consecutive_losses
        metrics["max_consecutive_losses"] = max_consecutive
        
        if self.account.consecutive_losses >= max_consecutive:
            self._block_account(f"{max_consecutive} pérdidas consecutivas")
            return RiskVerdict(
                allow=False,
                reason=f"{self.account.consecutive_losses} pérdidas consecutivas ≥ {max_consecutive}",
                risk_metrics=metrics
            )
        
        # 7. FILTRO NOTICIAS HIGH IMPACT USD
        if self.config.news_filter.avoid_high_impact_usd_news:
            trade_date = signal.timestamp.date() if hasattr(signal.timestamp, 'date') else signal.timestamp
            if self.is_high_impact_news_day(trade_date, "USD"):
                return RiskVerdict(
                    allow=False,
                    reason="Noticia alto impacto USD hoy - filtro activado",
                    risk_metrics={**metrics, "news_filter": True}
                )
        
        # 8. VALIDAR SEÑAL TIENE TODO REQUERIDO
        required = ["entry_price", "sl_price", "tp_price", "lot_size", "direction", "symbol"]
        for field in required:
            if not getattr(signal, field, None):
                return RiskVerdict(
                    allow=False,
                    reason=f"Señal incompleta: falta {field}",
                    risk_metrics=metrics
                )
        
        # 9. VALIDAR R:R MÍNIMO (debe ser 1:2 por config)
        sl_dist = abs(signal.entry_price - signal.sl_price)
        tp_dist = abs(signal.tp_price - signal.entry_price)
        if sl_dist > 0:
            actual_rr = tp_dist / sl_dist
            metrics["actual_rr"] = actual_rr
            metrics["required_rr"] = self.config.risk_reward.ratio
            if actual_rr < self.config.risk_reward.ratio * 0.95:  # 5% tolerancia
                return RiskVerdict(
                    allow=False,
                    reason=f"R:R {actual_rr:.2f} < requerido {self.config.risk_reward.ratio}",
                    risk_metrics=metrics
                )
        
        # TODO PASÓ
        return RiskVerdict(allow=True, reason="Validación pre-trade OK", risk_metrics=metrics)
    
    def validate_position_update(self, position: Position, current_price: float) -> RiskVerdict:
        """Validaciones continuas en posición abierta (para live)."""
        # Placeholder para live trading - en backtest no se usa
        return RiskVerdict(allow=True, reason="OK", risk_metrics={})
    
    def on_trade_closed(self, pnl_usd: float, exit_reason: SignalType):
        """Actualiza estado de cuenta tras cierre de trade."""
        self.account.balance += pnl_usd
        self.account.equity = self.account.balance  # Simplificado (sin posiciones abiertas)
        self.account.daily_pnl += pnl_usd
        self.account.monthly_pnl += pnl_usd
        self.account.daily_trades += 1
        
        # Actualizar pérdidas consecutivas
        if pnl_usd < 0:
            self.account.consecutive_losses += 1
        else:
            self.account.consecutive_losses = 0
        
        # Re-check kill switches tras cada trade
        self._check_kill_switches()
    
    def _check_kill_switches(self):
        """Re-verifica kill switches tras cada trade."""
        daily_loss_limit = self.config.limits.daily_loss_limit_pct
        monthly_loss_limit = self.config.limits.monthly_loss_limit_pct
        max_consecutive = self.config.limits.max_consecutive_losses
        
        daily_pnl_pct = self.account.daily_pnl / self.account.balance if self.account.balance > 0 else 0
        monthly_pnl_pct = self.account.monthly_pnl / self.account.balance if self.account.balance > 0 else 0
        
        if daily_pnl_pct <= -daily_loss_limit:
            self._block_account(f"Límite pérdida diaria {daily_loss_limit*100}% alcanzado tras trade")
        elif monthly_pnl_pct <= -monthly_loss_limit:
            self._block_account(f"Límite pérdida mensual {monthly_loss_limit*100}% alcanzado tras trade")
        elif self.account.consecutive_losses >= max_consecutive:
            self._block_account(f"{max_consecutive} pérdidas consecutivas tras trade")
    
    def _block_account(self, reason: str):
        """Bloquea la cuenta - reactivación SOLO manual."""
        self.account.is_blocked = True
        self.account.block_reason = reason
        print(f"🚨 CUENTA BLOQUEADA: {reason}")
    
    def manual_reactivate(self, authorized_by: str = "Mariely"):
        """Reactivación manual (solo ella puede autorizar)."""
        if authorized_by == "Mariely":
            self.account.is_blocked = False
            self.account.block_reason = ""
            self.account.consecutive_losses = 0
            self.account.daily_pnl = 0.0
            self.account.daily_trades = 0
            # monthly_pnl NO se resetea (límite mensual real)
            print(f"✅ Cuenta reactivada manualmente por {authorized_by}")
        else:
            raise PermissionError("Solo Mariely puede reactivar la cuenta")
    
    def reset_daily(self):
        """Reset diario (nuevo día de trading)."""
        today = datetime.now().date()
        if self.account.last_reset_day != today:
            self.account.daily_pnl = 0.0
            self.account.daily_trades = 0
            self.account.last_reset_day = today
    
    def reset_monthly(self):
        """Reset mensual (nuevo mes)."""
        current_month = datetime.now().replace(day=1).date()
        if self.account.last_reset_month != current_month:
            self.account.monthly_pnl = 0.0
            self.account.last_reset_month = current_month
    
    def get_account_summary(self) -> Dict:
        """Resumen de estado para dashboard/logs."""
        return {
            "balance": self.account.balance,
            "equity": self.account.equity,
            "daily_pnl": self.account.daily_pnl,
            "daily_pnl_pct": self.account.daily_pnl / self.account.balance if self.account.balance else 0,
            "monthly_pnl": self.account.monthly_pnl,
            "monthly_pnl_pct": self.account.monthly_pnl / self.account.balance if self.account.balance else 0,
            "open_positions": len(self.account.open_positions),
            "daily_trades": self.account.daily_trades,
            "consecutive_losses": self.account.consecutive_losses,
            "is_blocked": self.account.is_blocked,
            "block_reason": self.account.block_reason
        }


def create_risk_engine(balance: float = 10000.0) -> RiskEngine:
    """Factory para crear risk engine con cuenta inicializada."""
    account = AccountState(balance=balance, equity=balance)
    return RiskEngine(account=account)