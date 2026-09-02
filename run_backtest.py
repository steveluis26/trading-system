#!/usr/bin/env python3
"""Smoke test del pipeline completo: datos -> estrategia -> risk -> backtest -> metricas."""
import json, collections
from data.synthetic import generate
from strategies.example_ma import ExampleMA
from risk.engine import RiskEngine, RiskLimits
from backtest.engine import Backtester, Costs
from backtest.walkforward import rolling_windows
from measurement.metrics import compute

bars = generate(6000)
print(f"Barras: {len(bars)}  {bars[0].time:%Y-%m-%d} -> {bars[-1].time:%Y-%m-%d}")

bt = Backtester(ExampleMA(), RiskEngine(RiskLimits()), Costs(), 10_000)
res = bt.run(bars)

print("\n=== METRICAS (netas de spread, comision, slippage, swap) ===")
m = compute(res.positions, 10_000)
for k, v in m.items(): print(f"  {k:28} {v}")

print(f"\n=== RISK ENGINE: {len(res.rejections)} señales vetadas ===")
for r, n in collections.Counter(x["reason"].split("(")[0].strip()
                                for x in res.rejections).most_common(6):
    print(f"  {n:5}  {r}")

print("\n=== WALK-FORWARD (train 180d / test 60d) ===")
for i, (tr, te) in enumerate(rolling_windows(bars, 180, 60, 60), 1):
    r = Backtester(ExampleMA(), RiskEngine(RiskLimits()), Costs(), 10_000).run(te)
    mm = compute(r.positions, 10_000)
    print(f"  ventana {i}: test {len(te):5} barras | {mm['n_trades']:3} trades | "
          f"PnL {mm.get('pnl_neto',0):>9} | PF {mm.get('profit_factor','-')}")
