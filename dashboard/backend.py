"""Backend del dashboard (FastAPI). Panel de contexto (Caso A) + backtest por ano
(contexto completo preservado en fronteras, solo estrategia de ejecucion/cache).

Endpoints:
  GET /api/health
  GET /api/panels                     -> panel de contexto de los 3 pares (tiempo real)
  GET /api/backtest/{symbol}          -> total acumulado del par (suma de anos cacheados)
  GET /api/backtest/{symbol}/{year}   -> backtest de ese ano (contexto completo hasta fin de ano)
  GET /api/backtest/ALL               -> total conjunto acumulado de 3 pares
  GET /api/backtest/ALL/{year}        -> total conjunto de ese ano
  GET /api/equity/{symbol}/{window}   -> pnl por ventana (dia/semana/mes/trimestre/ano)
"""
from __future__ import annotations
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core.types import Timeframe
from data.loader import load_set
from features.realtime_panel import compute_panel
from risk.config import RiskConfig
from run_smc_backtest import run_symbol
from backtest.multitf import MultiTFBacktester
from strategies.smc_multitf import SMCMultiTF
from measurement.metrics import compute, daily_equity, pnl_by_window, sharpe_from_equity, max_dd_from_equity, CRITERIOS

app = FastAPI(title="Trading System Dashboard API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
YEARS = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]


@app.get("/api/health")
def health():
    return {"status": "ok", "symbols": SYMBOLS, "years": YEARS}


@app.get("/api/panel/{symbol}")
def panel(symbol: str):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    data = load_set(symbol, "data/raw")
    if Timeframe.M5 not in data:
        raise HTTPException(404, f"sin datos M5 para {symbol}")
    return compute_panel(symbol, data).to_dict()


@app.get("/api/panels")
def panels():
    out = {}
    for s in SYMBOLS:
        try:
            out[s] = panel(s)
        except HTTPException:
            out[s] = {"symbol": s, "error": "sin datos M5"}
    return out


def _load(symbol: str):
    """Carga y alinea el set completo del simbolo (contexto hasta el fin de datos)."""
    set_ = load_set(symbol, "data/raw")
    needed = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5]
    missing = [tf.value for tf in needed if tf not in set_]
    if missing:
        return None, missing
    m5 = set_[Timeframe.M5]
    t0, t1 = m5[0].time, m5[-1].time
    aligned = {tf: [b for b in set_[tf] if t0 <= b.time <= t1] for tf in needed}
    return aligned, None


def _run_year(symbol: str, year: str) -> dict:
    cache_file = os.path.join(CACHE_DIR, f"bt_{symbol}_{year}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    aligned, missing = _load(symbol)
    if aligned is None:
        return {"symbol": symbol, "year": year, "error": f"faltan marcos {missing}"}
    from datetime import datetime, timezone
    try:
        y = int(year)
    except ValueError:
        return {"symbol": symbol, "year": year, "error": "ano invalido"}
    ti = datetime(y, 1, 1, tzinfo=timezone.utc)
    tf = datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc)
    bt = MultiTFBacktester(SMCMultiTF(), RiskConfig.from_yaml(), initial_equity=10_000.0)
    res = bt.run(aligned, Timeframe.M5, drive_range=(ti, tf))
    m = compute(res.positions, 10_000.0, RiskConfig.from_yaml())
    m["symbol"] = symbol
    m["year"] = year
    m["daily"] = daily_equity(res)
    m["rejections"] = dict(collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections))
    with open(cache_file, "w") as f:
        json.dump(m, f)
    return m


def _agg(symbol: str) -> dict:
    """Total acumulado del par: corre el backtest COMPLETO del par (2020-2026)
    con contexto completo y calcula TODAS las metricas via compute(). Cache en
    bt_<SYM>_ALL.json. Esto da win_rate/sharpe/PF/DD reales (no solo suma de anos)."""
    cache_file = os.path.join(CACHE_DIR, f"bt_{symbol}_ALL.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    res = run_symbol(symbol, 10_000.0)
    if res is None:
        return {"symbol": symbol, "error": "sin datos completos"}
    m = compute(res.positions, 10_000.0, RiskConfig.from_yaml())
    m["symbol"] = symbol
    m["daily"] = daily_equity(res)
    m["rejections"] = dict(collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections))
    with open(cache_file, "w") as f:
        json.dump(m, f)
    return m


@app.get("/api/backtest/{symbol}")
def backtest(symbol: str):
    symbol = symbol.upper()
    if symbol == "ALL":
        return _agg_all()
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    return _agg(symbol)


@app.get("/api/backtest/{symbol}/{year}")
def backtest_year(symbol: str, year: str):
    symbol = symbol.upper()
    if symbol == "ALL":
        return _agg_year_all(year)
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    return _run_year(symbol, year)


def _load_year_cache(symbol: str, year: str) -> dict | None:
    """Lee el cache por par/ano ya calculado (bt_<SYM>_<YEAR>.json). None si falta."""
    cf = os.path.join(CACHE_DIR, f"bt_{symbol}_{year}.json")
    if not os.path.exists(cf):
        return None
    with open(cf) as f:
        return json.load(f)


def _agg_year_all(year: str) -> dict:
    """Total conjunto de UN ano: suma los deltas diarios de los 3 pares ese ano
    leyendo los caches por par (bt_<SYM>_<YEAR>.json), que ya estan correctos.
    NO usa caches intermedios bt_ALL_* (fuente de datos planos obsoletos)."""
    cache_file = os.path.join(CACHE_DIR, f"bt_ALL_{year}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    daily_delta = collections.OrderedDict()
    total = {"symbol": "ALL", "year": year, "n_trades": 0,
             "pnl_neto": 0.0, "daily": []}
    for s in SYMBOLS:
        r = _load_year_cache(s, year)
        if not r or "error" in r or "pnl_neto" not in r:
            continue
        total["n_trades"] += r.get("n_trades", 0)
        total["pnl_neto"] += r.get("pnl_neto", 0.0)
        for d, eq in r.get("daily", []):
            daily_delta[d] = daily_delta.get(d, 0.0) + (eq - 10_000.0)
    total["daily"] = [(d, round(10_000.0 + v, 2)) for d, v in daily_delta.items()]
    if daily_delta:
        last_eq = 10_000.0 + daily_delta[list(daily_delta)[-1]]
        total["retorno_pct"] = round((last_eq / 10_000.0 - 1) * 100, 2)
        total["periodo_dias"] = len(daily_delta)
    with open(cache_file, "w") as f:
        json.dump(total, f)
    return total


def _agg_all() -> dict:
    """Total conjunto acumulado: suma los deltas diarios de los 3 pares (daily del
    total) y calcula sharpe/DD desde esa curva. win_rate/PF se ponderan por trades
    de los 3 pares (no hay posiciones combinadas)."""
    cache_file = os.path.join(CACHE_DIR, f"bt_ALL_ALL.json")
    daily_delta = collections.OrderedDict()
    total = {"symbol": "ALL", "n_trades": 0, "pnl_neto": 0.0, "daily": [],
             "win_rate_pct": 0.0, "profit_factor": 0.0, "trades_por_par": {}}
    pw, pwins = 0, 0  # para win_rate ponderado
    pf_w, pf_l = 0.0, 0.0  # gross profit / loss ponderados
    for s in SYMBOLS:
        r = _agg(s)  # backtest completo del par (metricas reales)
        if "error" in r or "n_trades" not in r:
            continue
        total["n_trades"] += r.get("n_trades", 0)
        total["pnl_neto"] += r.get("pnl_neto", 0.0)
        total["trades_por_par"][s] = r.get("n_trades", 0)
        pw += r.get("n_trades", 0)
        pwins += r.get("n_trades", 0) * (r.get("win_rate_pct", 0) / 100.0)
        pf_w += r.get("gross_profit", 0.0)
        pf_l += r.get("gross_loss", 0.0)
        # daily del par (solo 2024-2026 para GBPUSD) suma al total
        for d, eq in r.get("daily", []):
            daily_delta[d] = daily_delta.get(d, 0.0) + (eq - 10_000.0)
    total["daily"] = [(d, round(10_000.0 * len(SYMBOLS) + v, 2)) for d, v in daily_delta.items()]
    if daily_delta:
        last_eq = 10_000.0 * len(SYMBOLS) + daily_delta[list(daily_delta)[-1]]
    total["retorno_pct"] = round((last_eq / (10_000.0 * len(SYMBOLS)) - 1) * 100, 2)
    total["periodo_dias"] = len(daily_delta)
    total["sharpe_anual"] = sharpe_from_equity(total["daily"])
    total["max_drawdown_pct"] = max_dd_from_equity(total["daily"])
    total["retorno_pct"] = round(total["pnl_neto"] / (10_000.0 * len(SYMBOLS)) * 100, 2)
    if pw > 0:
        total["win_rate_pct"] = round(pwins / pw * 100, 2)
    if pf_l > 0:
        total["profit_factor"] = round(pf_w / abs(pf_l), 3)
    # veredicto del total: solo si tenemos las 4 metricas (sin expectancy combinada)
    if "sharpe_anual" in total and "max_drawdown_pct" in total and "profit_factor" in total:
        f = []
        if (total["sharpe_anual"] or -9) < CRITERIOS["sharpe_min"]:
            f.append(f"Sharpe {total['sharpe_anual']}<1.0")
        if total["max_drawdown_pct"] > CRITERIOS["dd_max_pct"]:
            f.append(f"DD {total['max_drawdown_pct']}%>15%")
        if total["profit_factor"] < CRITERIOS["pf_min"]:
            f.append(f"PF {total['profit_factor']}<1.2")
        total["veredicto"] = ("SIN EDGE -> " + "; ".join(f)) if f else "EDGE PLAUSIBLE (conjunto)"
    with open(cache_file, "w") as f:
        json.dump(total, f)
    return total


@app.get("/api/equity/{symbol}/{window}")
def equity_window(symbol: str, window: str):
    symbol = symbol.upper()
    if window not in ("dia", "semana", "mes", "trimestre", "ano"):
        raise HTTPException(400, "ventana invalida")
    m = _agg_all() if symbol == "ALL" else _agg(symbol)
    if "error" in m:
        return {"error": m["error"]}
    return {"symbol": symbol, "window": window, "rows": pnl_by_window(m.get("daily", []), window)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
