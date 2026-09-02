"""Walk-forward multi-timeframe: la unica validacion honesta para series temporales.
K-fold aleatorio y train_test_split FILTRAN informacion futura -> backtest
espectacular, live desastroso.

rolling_windows_mtf(bars_by_tf, ...) recibe el dict {Timeframe: [Bar]} y genera
pares (train_set, test_set), cada uno un dict de los mismos marcos, alineados
por rango de tiempo del marco DRIVER (M5).
"""
from __future__ import annotations
from core.types import Bar, Timeframe


def rolling_windows_mtf(bars_by_tf: dict[Timeframe, list[Bar]],
                        driver: Timeframe = Timeframe.M5,
                        train_days: int = 180, test_days: int = 60,
                        step_days: int = 60):
    if not bars_by_tf or driver not in bars_by_tf:
        return
    drv = bars_by_tf[driver]
    if not drv: return
    t0 = drv[0].time
    day = lambda b: (b.time - t0).days
    total = day(drv[-1])
    start = 0
    while start + train_days + test_days <= total:
        tr, te = {}, {}
        for tf, bars in bars_by_tf.items():
            tr[tf] = [b for b in bars if start <= day(b) < start + train_days]
            te[tf] = [b for b in bars if start + train_days <= day(b) < start + train_days + test_days]
        if all(tr.values()) and all(te.values()):
            yield tr, te
        start += step_days


def rolling_windows(bars: list[Bar], train_days: int = 180, test_days: int = 60,
                    step_days: int = 60):
    """Genera (train, test) deslizantes. En Fase 3 el modelo se reentrena
    con `train` y se evalua SOLO en `test`, nunca al reves."""
    if not bars: return
    t0 = bars[0].time
    day = lambda b: (b.time - t0).days
    total = day(bars[-1])
    start = 0
    while start + train_days + test_days <= total:
        tr = [b for b in bars if start <= day(b) < start + train_days]
        te = [b for b in bars if start + train_days <= day(b) < start + train_days + test_days]
        if tr and te: yield tr, te
        start += step_days
