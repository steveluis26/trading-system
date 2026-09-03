#!/usr/bin/env python3
"""Backtest Estrategia 2 Wyckoff — mismo rango comun que SMC para comparar."""
from __future__ import annotations
import argparse, collections
from datetime import datetime, timezone
from data.loader import load_set
from strategies.wyckoff_v2 import WyckoffV2
from risk.config import RiskConfig
from backtest.multitf import MultiTFBacktester
from measurement.metrics import compute
from core.types import Timeframe

SYMS=["EURUSD","GBPUSD","XAUUSD"]
COMMON_START=datetime(2024,8,26,tzinfo=timezone.utc)
COMMON_END=datetime(2026,5,15,23,59,tzinfo=timezone.utc)

def run_symbol(symbol, equity):
    set_=load_set(symbol,"data/raw")
    needed=[Timeframe.D1,Timeframe.H4,Timeframe.H1,Timeframe.M15,Timeframe.M5]
    missing=[tf.value for tf in needed if tf not in set_]
    if missing:
        print(f"  [{symbol}] FALTAN {missing}"); return None
    for tf in needed:
        set_[tf]=[b for b in set_[tf] if COMMON_START<=b.time<=COMMON_END]
    m5=set_[Timeframe.M5]
    if not m5: return None
    t0,t1=m5[0].time,m5[-1].time
    aligned={tf:[b for b in set_[tf] if t0<=b.time<=t1] for tf in needed}
    print(f"  [{symbol}] {t0:%Y-%m-%d}->{t1:%Y-%m-%d} M5={len(aligned[Timeframe.M5])}")
    bt=MultiTFBacktester(WyckoffV2(),RiskConfig.from_yaml(),initial_equity=equity)
    return bt.run(aligned,Timeframe.M5)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbol",default="ALL")
    ap.add_argument("--equity",type=float,default=10000)
    a=ap.parse_args()
    syms=SYMS if a.symbol=="ALL" else [a.symbol]
    all_pos=[]
    for sym in syms:
        print(f"\n=== {sym} (Wyckoff v2) ===")
        res=run_symbol(sym,a.equity)
        if res is None: continue
        m=compute(res.positions,a.equity,RiskConfig.from_yaml())
        for k,v in m.items(): print(f"  {k:26} {v}")
        print(f"  rechazos: {len(res.rejections)}")
        all_pos.extend(res.positions)
    if a.symbol=="ALL" and all_pos:
        print("\n=== TOTAL v2 ===")
        mt=compute(all_pos,a.equity*len(syms),RiskConfig.from_yaml())
        for k,v in mt.items(): print(f"  {k:26} {v}")

if __name__=="__main__": main()
