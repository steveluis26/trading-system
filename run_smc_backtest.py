#!/usr/bin/env python3
"""Corre el backtest SMC sobre datos REALES (2 anos D1/H4/H1/M15 + 3m M5).
Reporta metricas NETAS (spread + comision + slippage + swap) por par y total,
con veredicto go/no-go contra los criterios de aceptacion.

Uso:
  python run_smc_backtest.py            # EURUSD con equity 10k
  python run_smc_backtest.py --symbol XAUUSD --equity 10000
"""
from __future__ import annotations
import argparse, collections
from datetime import datetime, timezone
from data.loader import load_set
from strategies.smc_multitf import SMCMultiTF
from risk.config import RiskConfig
from backtest.multitf import MultiTFBacktester
from backtest.walkforward import rolling_windows_mtf
from measurement.metrics import compute
from core.types import Timeframe

SYMS = ["EURUSD", "GBPUSD", "XAUUSD"]

# Rango COMUN donde TODOS los pares tienen D1/H4/H1/M15/M5 completos
# (evtradelabs da D1 desde 2024-08-26; XAUUSD M5 termina 2026-05-15, asi que
# esa es la fecha final comun para no mezclar tramos ni usar fallback D1).
# Solo estrategia de ejecucion: recorta los datos. NO cambia parametros SMC.
COMMON_START = datetime(2024, 8, 26, tzinfo=timezone.utc)
COMMON_END = datetime(2026, 5, 15, 23, 59, tzinfo=timezone.utc)

def run_symbol(symbol, equity):
    set_ = load_set(symbol, "data/raw")
    needed = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5]
    missing = [tf.value for tf in needed if tf not in set_]
    if missing:
        print(f"  [{symbol}] FALTAN marcos: {missing} -> no se puede correr")
        return None
    # recortar al rango comun (sin fallback D1, fecha final comun)
    for tf in needed:
        set_[tf] = [b for b in set_[tf] if COMMON_START <= b.time <= COMMON_END]
    # alinear todos los marcos al mismo rango del M5 (que es el mas corto)
    m5 = set_[Timeframe.M5]
    if not m5:
        print(f"  [{symbol}] sin velas M5 en rango comun")
        return None
    t0, t1 = m5[0].time, m5[-1].time
    aligned = {tf: [b for b in set_[tf] if t0 <= b.time <= t1] for tf in needed}
    print(f"  [{symbol}] rango {t0:%Y-%m-%d} -> {t1:%Y-%m-%d} | "
          f"M5={len(aligned[Timeframe.M5])} velas | D1={len(aligned[Timeframe.D1])}")
    bt = MultiTFBacktester(SMCMultiTF(), RiskConfig.from_yaml(), initial_equity=equity)
    res = bt.run(aligned, Timeframe.M5)
    return res

def run_one(symbol, equity=10_000.0) -> dict:
    """Devuelve el dict de metricas del backtest para el API del dashboard."""
    res = run_symbol(symbol, equity)
    if res is None:
        return {"symbol": symbol, "error": "sin datos completos"}
    m = compute(res.positions, equity, RiskConfig.from_yaml())
    m["symbol"] = symbol
    m["rejections"] = collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections
    )
    m["rejections"] = dict(m["rejections"])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ALL")
    ap.add_argument("--equity", type=float, default=10_000.0)
    a = ap.parse_args()
    syms = SYMS if a.symbol == "ALL" else [a.symbol]

    all_pos = []
    for sym in syms:
        print(f"\n=== {sym} ===")
        res = run_symbol(sym, a.equity)
        if res is None:
            continue
        m = compute(res.positions, a.equity, RiskConfig.from_yaml())
        for k, v in m.items():
            print(f"  {k:26} {v}")
        print(f"  rechazos risk engine: {len(res.rejections)}")
        for r, n in collections.Counter(x['reason'].split('(')[0].strip()
                                        for x in res.rejections).most_common(6):
            print(f"    {n:5} {r}")
        all_pos.extend(res.positions)

    if a.symbol == "ALL" and all_pos:
        print(f"\n=== TOTAL (3 pares combinados) ===")
        mt = compute(all_pos, a.equity * len(syms), RiskConfig.from_yaml())
        for k, v in mt.items():
            print(f"  {k:26} {v}")

if __name__ == "__main__":
    main()
