"""Generador de barras sinteticas. SOLO para probar que el pipeline corre.
NUNCA para evaluar una estrategia: no tiene la microestructura del mercado real."""
from __future__ import annotations
import random, datetime as dt
from core.types import Bar, Timeframe

def generate(n: int = 4000, start_price: float = 1.0850, seed: int = 42,
             symbol: str = "EURUSD", tf: Timeframe = Timeframe.H1) -> list[Bar]:
    random.seed(seed)
    bars, price, t = [], start_price, dt.datetime(2024, 1, 1, 0, 0)
    for _ in range(n):
        t += dt.timedelta(hours=1)
        if t.weekday() >= 5: continue
        drift = random.gauss(0, 0.0009)
        o = price; c = o + drift
        h = max(o, c) + abs(random.gauss(0, 0.0004))
        l = min(o, c) - abs(random.gauss(0, 0.0004))
        bars.append(Bar(time=t, open=o, high=h, low=l, close=c,
                        volume=random.randint(500, 5000),
                        spread=random.uniform(8, 20), symbol=symbol, timeframe=tf))
        price = c
    return bars
