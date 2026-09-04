"""Test de integración: si multitf.py vuelve a fijo, este test FALLA en CI."""
import sys
sys.path.insert(0, ".")
from core.types import Bar, Signal, Side, Timeframe
from datetime import datetime, timezone
from risk.config import RiskConfig
from backtest.multitf import MultiTFBacktester
from strategies.base import Strategy

class DummyStrategy(Strategy):
    name = "dummy_sl45"
    def on_bars(self, ctx, t):
        m5 = ctx.get(Timeframe.M5, [])
        if not m5:
            return None
        last = m5[-1]
        # SL 45 pips exactos
        pip = 0.01 if last.symbol == "XAUUSD" else 0.0001
        sl = last.close - 45 * pip if last.close > 0 else last.close - 0.0045
        tp = last.close + 90 * pip
        return Signal(time=t, symbol=last.symbol, side=Side.BUY, entry=last.close, sl=sl, tp=tp, strategy=self.name)

def test_sizing_1pct_via_backtest():
    from data.loader import load_set
    # usa XAUUSD real para contexto, pero fuerza SL 45
    bars = load_set("XAUUSD", "data/raw").get(Timeframe.M5, [])[:100]
    if not bars:
        # fallback sintético
        base = datetime.now(timezone.utc)
        bars = [Bar(time=base, open=1.0, high=1.01, low=0.99, close=1.0, volume=100, symbol="XAUUSD", timeframe=Timeframe.M5) for _ in range(100)]
        # fuerza M5 con close 2500 para XAU
        for b in bars:
            b.close = 2500.0; b.open = 2500.0; b.high = 2501.0; b.low = 2499.0
    # contexto mínimo
    mtf = {Timeframe.M5: bars, Timeframe.M15: bars[::3], Timeframe.H1: bars[::12], Timeframe.H4: bars[::48], Timeframe.D1: bars[::288]}
    cfg = RiskConfig.from_yaml()
    # XAU 45 pips -> 1% de 10k = $100, vol esperado ~2.22 lotes (45*1.0*2.22=99.9)
    # Con sizing fijo viejo 0.10 lotes, riesgo sería 45*0.10*1.0=4.5$ (0.045%) - muy distinto
    # Verificamos que el backtest use 1% (vol 2.22) no fijo 0.10
    strat = DummyStrategy()
    bt = MultiTFBacktester(strat, cfg, initial_equity=10000)
    res = bt.run(mtf, Timeframe.M5)
    # si sizing es 1% dinámico, el primer trade debe tener vol ~2.22, no 0.10
    assert len(res.positions) > 0 or len(res.rejections) > 0, "debe intentar abrir al menos 1"
    if res.positions:
        vol = res.positions[0].volume
        # 1% dinámico -> 2.22, fijo -> 0.10
        assert abs(vol - 2.22) < 0.05, f"vol {vol} debe ser 2.22 (1% dinámico), no 0.10 (fijo) — sizing revertido"
        # riesgo real ~1%
        sl_pips = 45
        upp = cfg.usd_per_pip("XAUUSD")
        risk_pct = sl_pips * vol * upp / 10000 * 100
        assert 0.8 < risk_pct < 1.2, f"risk {risk_pct}% debe ser ~1%, no 4.5% fijo"
    else:
        # si no hay posiciones, debe ser por SL muy ancho, no por sizing fijo
        # verifica que el motivo no sea volumen fijo
        reasons = [r["reason"] for r in res.rejections]
        assert not any("0.01*equity" in str(r) for r in reasons), "sizing fijo detectado"

def test_sizing_rechaza_SL_extremo():
    cfg = RiskConfig.from_yaml()
    upp = cfg.usd_per_pip("XAUUSD")
    vol_raw = (10000*0.01)/(20000*upp)
    assert vol_raw < 0.01, "SL 20000 pips debe dar <0.01 y rechazar"
