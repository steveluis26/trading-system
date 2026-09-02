"""Carga de datos historicos desde CSV (formato del proyecto).

Formato esperado:  timestamp,open,high,low,close,volume
  - timestamp: ISO UTC, ej. 2024-08-26 06:00:00+00:00
  - OHLC: precios mid (no trae bid/ask -> ver nota spread abajo)
  - volume: 0 en forex (esperado), real en XAUUSD

NO trae spread. El spread se aplica en el backtester desde config/risk.yaml
(costs.spread_points por simbolo). Esto es correcto: en produccion el spread
lo da el broker en vivo; en backtest lo modelamos como costo conservador.

Uso:
  from data.loader import load_csv, load_set
  bars = load_csv("data/raw/EURUSD_1h_2y.csv", Timeframe.H1, "EURUSD")
  # o cargar un set multi-timeframe:
  set_ = load_set("EURUSD", base="data/raw")  # busca EURUSD_*_2y.csv
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path
from core.types import Bar, Timeframe

_TF_BY_SUFFIX = {
    "m1": Timeframe.M1, "1m": Timeframe.M1,
    "m5": Timeframe.M5, "5m": Timeframe.M5,
    "m15": Timeframe.M15, "15m": Timeframe.M15,
    "m30": Timeframe.M30, "30m": Timeframe.M30,
    "h1": Timeframe.H1, "1h": Timeframe.H1,
    "h4": Timeframe.H4, "4h": Timeframe.H4,
    "d1": Timeframe.D1, "1d": Timeframe.D1, "d": Timeframe.D1,
}
# nombre esperado: SYMBOL_<tf>[_...].csv  ej. EURUSD_1h_2y.csv, XAUUSD_15m.csv
import re as _re
_TF_RE = _re.compile(r"_(" + "|".join(_TF_BY_SUFFIX) + r")(?:_|$)")


def _tf_from_name(path: Path) -> Timeframe:
    m = _TF_RE.search(path.stem.lower())
    return _TF_BY_SUFFIX.get(m.group(1), Timeframe.H1) if m else Timeframe.H1


def load_csv(path: str | Path, timeframe: Timeframe | None = None,
             symbol: str | None = None) -> list[Bar]:
    path = Path(path)
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    # normalizar timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "close"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    if timeframe is None:
        timeframe = _tf_from_name(path)
    if symbol is None:
        symbol = path.stem.split("_")[0].upper()

    bars = [
        Bar(time=ts, open=o, high=h, low=l, close=c, volume=v,
            spread=0.0, symbol=symbol, timeframe=timeframe)
        for ts, o, h, l, c, v in zip(
            df["timestamp"], df["open"], df["high"],
            df["low"], df["close"], df["volume"].fillna(0))
    ]
    return bars


def load_set(symbol: str, base: str = "data/raw") -> dict[Timeframe, list[Bar]]:
    """Carga todos los CSV que empiecen con <SYMBOL>_*.csv en base/ y los
    CONCATENA por marco en orden cronologico (ej EURUSD_5m_2020.csv, ..._2021.csv).
    Esto permite tener M5 de varios anos en archivos separados y usarlos todos."""
    symbol = symbol.upper()
    from collections import defaultdict
    files: dict[Timeframe, list] = defaultdict(list)
    for p in sorted(Path(base).glob(f"{symbol}_*.csv")):
        tf = _tf_from_name(p)
        if tf is not None:
            files[tf].append(p)
    out: dict[Timeframe, list[Bar]] = {}
    for tf, paths in files.items():
        bars: list[Bar] = []
        for p in sorted(paths):  # orden cronologico por nombre (trae año)
            bars.extend(load_csv(p, tf, symbol))
        out[tf] = bars
    return out


def summary(bars_by_tf: dict[Timeframe, list[Bar]]) -> str:
    lines = [f" Sets cargados para {list(bars_by_tf.values())[0][0].symbol if bars_by_tf else '?'}:"]
    for tf in sorted(bars_by_tf, key=lambda t: t.value):
        b = bars_by_tf[tf]
        if b:
            lines.append(f"  {tf.value:3} : {len(b):6} barras  "
                         f"{b[0].time:%Y-%m-%d %H:%M} -> {b[-1].time:%Y-%m-%d %H:%M}")
    return "\n".join(lines)
