"""Backtester MULTI-TIMEFRAME (driving candle = M5).

El backtest avanza vela a vela en el timeframe DE ENTRADA (M5). En cada vela:
  1) cierra/actualiza posiciones abiertas (SL/TP/breakeven/parcial) sobre M5
  2) alimenta la estrategia con barras cerradas de TODOS los marcos
     (D1/H4/H1/M15/M5) hasta ese instante -> estructura SMC
  3) la estrategia decide senal (o None)
  4) risk engine (veto + sizing por formula de LOTES) -> fill

Anti-leakage: cada marco recibe SOLO barras con time <= driving_time.

NOTA sobre el breakeven/parcial: se maneja por posicion, no por estrategia.
El backtester conoce los parametros (trigger 40%, cierra 1/3) y los aplica
sobre la vela M5 donde el precio cruza el umbral. Es determinista.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from core.types import Bar, Side, Position, Signal, Timeframe
from strategies.base import Strategy
from risk.config import RiskConfig

PIP = 0.0001

@dataclass
class Costs:
    spread_points: float = 12.0
    commission_per_lot: float = 7.0
    slippage_points: float = 3.0
    swap_per_lot_per_day: float = -2.0
    point: float = 0.00001
    contract_size: float = 100_000

@dataclass
class BacktestResult:
    positions: list[Position] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    equity: list[tuple] = field(default_factory=list)
    initial: float = 10_000.0
    halted: bool = False
    halt_reason: str = ""

class MultiTFBacktester:
    def __init__(self, strategy: Strategy, cfg: RiskConfig, initial_equity: float = 10_000.0):
        self.s = strategy
        self.cfg = cfg
        self.initial = initial_equity

    def run(self, mtf: dict[Timeframe, list[Bar]], drive_tf: Timeframe = Timeframe.M5,
            drive_range: tuple | None = None) -> BacktestResult:
        """drive_range = (t_inicio, t_fin) opcional: solo se OPERAN las velas M5
        en ese rango, pero el CONTEXTO (todos los marcos) se construye con TODO
        el historial disponible hasta cada vela. Esto permite cachear por año sin
        perder el contexto M15 previo en la frontera de enero. NO altera la
        estrategia: on_bars recibe el mismo ctx que recibiria en un backtest unico."""
        res = BacktestResult(initial=self.initial)
        bars_all = mtf[drive_tf]
        if drive_range is not None:
            t0, t1 = drive_range
            bars = [b for b in bars_all if t0 <= b.time <= t1]
        else:
            bars = bars_all
        idx = {tf: 0 for tf in mtf}
        # cajas mutables para que _close/_partial_close actualicen el equity real
        equity_box = [self.initial]
        peak = [self.initial]
        daily_pnl = [0.0]; day = [None]
        consecutive_losses = [0]
        halted = False; halt_reason = ""
        ops_today = 0
        open_positions: list[Position] = []
        open_results: list[dict] = []

        self.s.reset()
        ctx: dict[Timeframe, list[Bar]] = {tf: [] for tf in mtf}

        def slice_until(tf, t):
            i = idx[tf]
            out = []
            while i < len(mtf[tf]) and mtf[tf][i].time <= t:
                out.append(mtf[tf][i]); i += 1
            idx[tf] = i
            return out

        for b in bars:
            t = b.time
            # reset diario
            if day[0] != t.date():
                day[0] = t.date(); daily_pnl[0] = 0.0; consecutive_losses[0] = 0; ops_today = 0
                if self.cfg.no_hold_over_weekend:
                    pass  # el cierre fin-semana se hace por hora abajo

            # --- 1) gestionar posiciones abiertas sobre esta vela M5 ---
            for p in list(open_positions):
                self._manage_position(p, b, t, open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses)

            # --- 2) senal de la estrategia con todos los marcos hasta t ---
            # extender ctx in-place (NO concatenar: evita O(n^2) de copia de lista)
            for tf in mtf:
                ctx[tf].extend(slice_until(tf, t))
            # NOTA: slice_until muta idx; para la estrategia usamos el estado ya avanzado
            sig = self.s.on_bars(ctx, t)
            if sig is None:
                res.equity.append((t, equity_box[0])); continue

            # --- 3) risk engine ---
            reason, vol = self._risk_check(sig, t, equity_box[0], peak[0], daily_pnl[0],
                                          consecutive_losses[0], halted, ops_today, open_positions)
            if reason:
                res.rejections.append({"time": t, "reason": reason,
                                       "strategy": sig.strategy,
                                       "correlation_id": sig.correlation_id})
                res.equity.append((t, equity_box[0])); continue

            # --- 4) fill ---
            sp = self.cfg.spread(sig.symbol) * PIP
            slip = self.cfg.slippage_points * PIP
            fill = sig.entry + sp/2 + slip if sig.side is Side.BUY else sig.entry - sp/2 - slip
            comm = -self.cfg.commission_per_lot * vol
            pos = Position(signal=sig, volume=vol, open_time=t, open_price=fill, commission=comm)
            open_positions.append(pos)
            ops_today += 1
            res.equity.append((t, equity_box[0])); continue

        # cerrar lo que quede
        for p in list(open_positions):
            self._close(p, bars[-1].close, bars[-1].time, "end_of_data", open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses)
        res.positions = open_results
        return res

    # ---------- gestion de posicion ----------
    def _manage_position(self, p, b, t, open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses):
        sl = p.sl if p.sl is not None else p.signal.sl
        tp = p.signal.tp
        side = p.signal.side
        hit_sl = b.low <= sl if side is Side.BUY else b.high >= sl
        hit_tp = b.high >= tp if side is Side.BUY else b.low <= tp

        # breakeven + parcial cuando el precio va >= 40% al TP
        if not p.breakeven_done:
            if side is Side.BUY:
                prog = (b.high - p.open_price) / (tp - p.open_price)
            else:
                prog = (p.open_price - b.low) / (p.open_price - tp)
            if prog >= self.cfg.be_trigger_pct_to_tp / 100.0:
                p.breakeven_done = True
                p.sl = p.open_price  # SL a breakeven (campo mutable de Position)
                frac = self.cfg.be_close_fraction / 100.0
                close_vol = round(p.volume * frac, 2)
                if close_vol > 0:
                    self._partial_close(p, close_vol, b, t, open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses)

        # SL/TP despues del breakeven
        if hit_sl:
            self._close(p, p.signal.sl, b.time, "sl", open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses)
        elif hit_tp:
            self._close(p, tp, b.time, "tp", open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses)

    def _partial_close(self, p, vol, b, t, open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses):
        sp = self.cfg.spread(p.signal.symbol) * PIP
        price = p.signal.sl if p.breakeven_done else p.open_price
        close_px = price + sp/2 if p.signal.side is Side.BUY else price - sp/2
        comm = -self.cfg.commission_per_lot * vol
        upp = self.cfg.usd_per_pip(p.signal.symbol)
        pip = self.cfg.pip(p.signal.symbol)
        diff_pips = (close_px - p.open_price) / pip if p.signal.side is Side.BUY else (p.open_price - close_px) / pip
        pnl = diff_pips * vol * upp + comm
        p.volume -= vol
        p.partial_pnl = (p.partial_pnl or 0) + pnl
        equity_box[0] += pnl
        daily_pnl[0] += pnl
        peak[0] = max(peak[0], equity_box[0])

    def _close(self, p, price, t, reason, open_positions, open_results, res, equity_box, peak, daily_pnl, consecutive_losses):
        sp = self.cfg.spread(p.signal.symbol) * PIP
        close_px = price - sp/2 if p.signal.side is Side.BUY else price + sp/2
        comm = -self.cfg.commission_per_lot * p.volume
        upp = self.cfg.usd_per_pip(p.signal.symbol)
        pip = self.cfg.pip(p.signal.symbol)
        diff_pips = (close_px - p.open_price) / pip if p.signal.side is Side.BUY else (p.open_price - close_px) / pip
        pnl = diff_pips * p.volume * upp + comm + (p.partial_pnl or 0)
        p.close_price = close_px; p.close_time = t; p.close_reason = reason + ("+partial" if (p.partial_pnl or 0) else "")
        equity_box[0] += pnl
        daily_pnl[0] += pnl
        peak[0] = max(peak[0], equity_box[0])
        consecutive_losses[0] = consecutive_losses[0] + 1 if pnl < 0 else 0
        if p in open_positions: open_positions.remove(p)
        open_results.append(p)
        res.equity.append((t, equity_box[0]))

    # ---------- risk engine ----------
    def _risk_check(self, sig, t, equity, peak, daily_pnl, consecutive_losses, halted, ops_today, open_positions):
        c = self.cfg
        if halted:
            return f"HALT: {halt_reason}", 0.0
        # drawdown mensual (kill switch)
        dd = (peak - equity) / peak * 100 if peak else 0
        if dd > c.kill_switch_dd_pct:
            return f"Drawdown {dd:.1f}% > {c.kill_switch_dd_pct}%", 0.0
        # perdida diaria
        if daily_pnl < 0 and abs(daily_pnl)/equity*100 > c.max_daily_loss_pct:
            return f"Perdida diaria {abs(daily_pnl)/equity*100:.1f}% > {c.max_daily_loss_pct}%", 0.0
        # 5 perdedoras seguidas => BLOQUEO (no pausa)
        if consecutive_losses >= c.max_consecutive_losses:
            return f"{consecutive_losses} perdidas consecutivas (BLOQUEO)", 0.0
        # exposicion
        if len(open_positions) >= c.max_open_positions:
            return f"Max {c.max_open_positions} abiertas", 0.0
        if any(p.signal.symbol == sig.symbol for p in open_positions):
            return f"Ya hay posicion en {sig.symbol}", 0.0
        if ops_today >= c.max_operations_per_day:
            return f"Max {c.max_operations_per_day} ops/dia", 0.0
        # horario / sesiones
        if t.weekday() == c.no_trade_weekday:
            return "Viernes bloqueado", 0.0
        if not c.in_session(t.hour):
            return f"Fuera de sesion ({t.hour}h)", 0.0
        # R:R
        rr = sig.risk_reward
        if rr < min(c.rr_target) - 0.001:
            return f"R:R {rr:.2f} < {min(c.rr_target)}", 0.0
        # sizing 1% dinámico — 0.022 XAU SL45 = $90 0.9% (lot_step 0.01)
        try:
            sl_pips = abs(sig.entry - sig.sl) / c.pip(sig.symbol) if c.pip(sig.symbol) else 0
            upp = c.usd_per_pip(sig.symbol)
            if sl_pips > 0 and upp > 0:
                vol_raw = (equity * 0.01) / (sl_pips * upp)
                if vol_raw < 0.01 - 1e-9:
                    return f"SL muy ancho ({sl_pips:.0f} pips) -> vol {vol_raw:.4f} < 0.01, 1% no ejecutable", 0.0
                vol = round(vol_raw / 0.01) * 0.01
                vol = max(0.01, min(vol, 100.0))
            else:
                vol = round(c.lots_per_1000_capital * equity / 1000, 2)
        except Exception:
            vol = round(c.lots_per_1000_capital * equity / 1000, 2)
        if vol < 0.01:
            return "Volumen < 0.01", 0.0
        return None, vol
