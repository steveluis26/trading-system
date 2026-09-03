"""
Backend del dashboard (FastAPI). Panel de contexto (Caso A) + backtest por año
(contexto completo preservado en fronteras, solo estrategia de ejecución/cache).

Endpoints:
  GET /api/health
  GET /api/panels                     -> panel de contexto de los 3 pares (tiempo real)
  GET /api/backtest/{symbol}          -> total acumulado del par (suma de años cacheados)
  GET /api/backtest/{symbol}/{year}   -> backtest de ese año (contexto completo hasta fin de año)
  GET /api/backtest/ALL               -> total conjunto acumulado de 3 pares
  GET /api/backtest/ALL/{year}        -> total conjunto de ese año
  GET /api/equity/{symbol}/{window}   -> pnl por ventana (dia/semana/mes/trimestre/año)
  GET /api/demo/wyckoff/{symbol}      -> análisis Wyckoff multi-timeframe
  GET /api/demo/backtest/custom       -> backtest personalizado con parámetros en vivo
  GET /api/demo/config/defaults       -> valores por defecto del config YAML
"""
from __future__ import annotations
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from core.types import Timeframe
from data.loader import load_set
from features.realtime_panel import compute_panel
from risk.config import RiskConfig
from run_smc_backtest import run_symbol
from backtest.multitf import MultiTFBacktester
from strategies.smc_multitf import SMCMultiTF
from measurement.metrics import compute, daily_equity, pnl_by_window, sharpe_from_equity, max_dd_from_equity, CRITERIOS
import yaml

def _get_strategy(name: str):
    name = (name or "v4").lower()
    if name in ("wyckoff", "wyckoff_v2", "v2"):
        try:
            from strategies.wyckoff_v2 import WyckoffV2
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "wyckoff.yaml")
            be_mode = "pct_40"
            if os.path.exists(cfg_path):
                with open(cfg_path) as f:
                    y = yaml.safe_load(f) or {}
                    be_mode = y.get("be_mode", be_mode)
            return WyckoffV2(be_mode=be_mode)
        except Exception as e:
            raise HTTPException(500, f"wyckoff load error: {e}")
    return SMCMultiTF()

def _strategy_prefix(name: str) -> str:
    s = (name or "v4").lower()
    return "wyckoff" if s in ("wyckoff", "wyckoff_v2", "v2") else "v4"

def _get_risk_for_strategy(strategy: str) -> RiskConfig:
    prefix = _strategy_prefix(strategy)
    base = RiskConfig.from_yaml()
    if prefix == "wyckoff":
        # Wyckoff usa su propio config, no risk.yaml BE/sessions/RR
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "wyckoff.yaml")) as f:
                y = yaml.safe_load(f) or {}
            # RR fib: permite 0.6 (fib 1.272) sin veto
            base.rr_target = [0.4, 3.0]
            # BE_MODE: pct_40 -> 40, fib_1272 -> 100 (en TP, efectivo casi OFF hasta TP)
            be_mode = y.get("be_mode", "pct_40")
            if be_mode == "pct_40":
                base.be_trigger_pct_to_tp = 40.0
                base.be_close_fraction = 33.3
            elif be_mode == "fib_1272":
                base.be_trigger_pct_to_tp = 100.0
                base.be_close_fraction = 33.3
            else:
                base.be_trigger_pct_to_tp = 40.0
            # Sesiones Wyckoff UTC
            pend = y.get("pending", {})
            sess = pend.get("sessions_utc", {})
            if sess:
                if "london" in sess:
                    base.session_london = tuple(sess["london"])
                if "newyork" in sess:
                    base.session_newyork = tuple(sess["newyork"])
                # asia not used in RiskConfig but keep for future
        except Exception:
            pass
        # Wyckoff RR fib: no vetar por RR bajo
        base.rr_target = [0.4, 3.0]
    return base

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


def _run_year(symbol: str, year: str, strategy: str = "v4") -> dict:
    prefix = _strategy_prefix(strategy)
    cache_file = os.path.join(CACHE_DIR, f"bt_{prefix}_{symbol}_{year}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    aligned, missing = _load(symbol)
    if aligned is None:
        return {"symbol": symbol,
        "lab_params": {"swing_lookback": swing_lookback, "atr_mult": atr_mult, "min_gap_atr": min_gap_atr, "min_bars_acc": min_bars_acc, "vol_lookback": vol_lookback, "vol_spike": vol_spike, "divergence_mult": divergence_mult, "bars_to_display": bars_to_display, "timeframe": timeframe}, "year": year, "strategy": prefix, "error": f"faltan marcos {missing}"}
    from datetime import datetime, timezone
    try:
        y = int(year)
    except ValueError:
        return {"symbol": symbol, "year": year, "error": "año invalido"}
    ti = datetime(y, 1, 1, tzinfo=timezone.utc)
    tf = datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc)
    strat = _get_strategy(strategy)
    risk_cfg = _get_risk_for_strategy(strategy)
    bt = MultiTFBacktester(strat, risk_cfg, initial_equity=10_000.0)
    res = bt.run(aligned, Timeframe.M5, drive_range=(ti, tf))
    m = compute(res.positions, 10_000.0, risk_cfg)
    m["symbol"] = symbol
    m["year"] = year
    m["strategy"] = prefix
    m["strategy_name"] = strat.name
    m["daily"] = daily_equity(res)
    m["rejections"] = dict(collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections))
    with open(cache_file, "w") as f:
        json.dump(m, f)
    return m


def _agg(symbol: str, strategy: str = "v4") -> dict:
    """Total acumulado del par: corre el backtest COMPLETO del par (2020-2026)
    con contexto completo y calcula TODAS las metricas via compute(). Cache en
    bt_<strategy>_<SYM>_ALL.json."""
    prefix = _strategy_prefix(strategy)
    cache_file = os.path.join(CACHE_DIR, f"bt_{prefix}_{symbol}_ALL.json")
    legacy = os.path.join(CACHE_DIR, f"bt_{symbol}_ALL.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    if prefix == "v4" and os.path.exists(legacy):
        with open(legacy) as f:
            d = json.load(f)
            try:
                with open(cache_file, "w") as out:
                    json.dump(d, out)
            except:
                pass
            return d
    if prefix == "v4":
        res = run_symbol(symbol, 10_000.0)
    else:
        aligned_tmp, missing = _load(symbol)
        if aligned_tmp is None:
            return {"symbol": symbol, "strategy": prefix, "error": f"faltan marcos {missing}"}
        strat_tmp = _get_strategy(strategy)
        risk_tmp = _get_risk_for_strategy(strategy)
        bt_tmp = MultiTFBacktester(strat_tmp, risk_tmp, initial_equity=10_000.0)
        res = bt_tmp.run(aligned_tmp, Timeframe.M5)
    if res is None:
        return {"symbol": symbol, "strategy": prefix, "error": "sin datos completos"}
    m = compute(res.positions, 10_000.0, risk_tmp)
    m["symbol"] = symbol
    m["strategy"] = prefix
    m["daily"] = daily_equity(res)
    m["rejections"] = dict(collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections))
    try:
        m["trades"] = [
            {"time": p.signal.time.isoformat() if hasattr(p.signal.time, "isoformat") else str(p.signal.time),
             "symbol": p.signal.symbol, "side": p.signal.side.value if hasattr(p.signal.side, "value") else str(p.signal.side),
             "entry": p.open_price, "sl": p.sl if p.sl is not None else p.signal.sl, "tp": p.signal.tp,
             "close": p.close_price, "close_reason": p.close_reason, "pnl": round(p.pnl(risk_tmp.usd_per_pip(p.signal.symbol), risk_tmp.pip(p.signal.symbol)),2),
             "volume": p.volume, "strategy": p.signal.strategy}
            for p in res.positions[:200]
        ]
    except:
        pass
    with open(cache_file, "w") as f:
        json.dump(m, f)
    return m


@app.get("/api/strategies")
def list_strategies():
    return {"strategies": ["v4", "wyckoff"], "default": "v4", "be_modes": ["pct_40", "fib_1272"]}

@app.get("/api/backtest/{symbol}")
def backtest(symbol: str, strategy: str = Query("v4", description="v4 o wyckoff")):
    symbol = symbol.upper()
    if symbol == "ALL":
        return _agg_all(strategy)
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    return _agg(symbol, strategy)


@app.get("/api/backtest/{symbol}/{year}")
def backtest_year(symbol: str, year: str, strategy: str = Query("v4")):
    symbol = symbol.upper()
    if symbol == "ALL":
        return _agg_year_all(year, strategy)
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    return _run_year(symbol, year, strategy)


def _load_year_cache(symbol: str, year: str) -> dict | None:
    """Lee el cache por par/año ya calculado (bt_<SYM>_<YEAR>.json). None si falta."""
    cf = os.path.join(CACHE_DIR, f"bt_{symbol}_{year}.json")
    if not os.path.exists(cf):
        return None
    with open(cf) as f:
        return json.load(f)


def _agg_year_all(year: str, strategy: str = "v4") -> dict:
    prefix = _strategy_prefix(strategy)
    cache_file = os.path.join(CACHE_DIR, f"bt_{prefix}_ALL_{year}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    daily_delta = collections.OrderedDict()
    total = {"symbol": "ALL", "year": year, "strategy": prefix, "n_trades": 0,
             "pnl_neto": 0.0, "daily": []}
    for s in SYMBOLS:
        cf = os.path.join(CACHE_DIR, f"bt_{prefix}_{s}_{year}.json")
        if os.path.exists(cf):
            with open(cf) as f:
                r = json.load(f)
        else:
            r = _load_year_cache(s, year)
            if prefix == "wyckoff":
                continue
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


def _agg_all(strategy: str = "v4") -> dict:
    """Total conjunto acumulado: suma los deltas diarios de los 3 pares (daily del
    total) y calcula sharpe/DD desde esa curva. win_rate/PF se ponderan por trades
    de los 3 pares (no hay posiciones combinadas)."""
    prefix = _strategy_prefix(strategy)
    cache_file = os.path.join(CACHE_DIR, f"bt_{prefix}_ALL_ALL.json")
    legacy = os.path.join(CACHE_DIR, f"bt_ALL_ALL.json")
    if prefix == "v4" and os.path.exists(cache_file) is False and os.path.exists(legacy):
        try:
            with open(legacy) as f:
                return json.load(f)
        except:
            pass
    daily_delta = collections.OrderedDict()
    total = {"symbol": "ALL", "strategy": prefix, "n_trades": 0, "pnl_neto": 0.0, "daily": [],
             "win_rate_pct": 0.0, "profit_factor": 0.0, "trades_por_par": {}}
    pw, pwins = 0, 0
    pf_w, pf_l = 0.0, 0.0
    for s in SYMBOLS:
        r = _agg(s, strategy)
        if "error" in r or "n_trades" not in r:
            continue
        total["n_trades"] += r.get("n_trades", 0)
        total["pnl_neto"] += r.get("pnl_neto", 0.0)
        total["trades_por_par"][s] = r.get("n_trades", 0)
        pw += r.get("n_trades", 0)
        pwins += r.get("n_trades", 0) * (r.get("win_rate_pct", 0) / 100.0)
        pf_w += r.get("gross_profit", 0.0)
        pf_l += r.get("gross_loss", 0.0)
        for d, eq in r.get("daily", []):
            daily_delta[d] = daily_delta.get(d, 0.0) + (eq - 10_000.0)
    total["daily"] = [(d, round(10_000.0 * len(SYMBOLS) + v, 2)) for d, v in daily_delta.items()]
    if daily_delta:
        last_eq = 10_000.0 * len(SYMBOLS) + daily_delta[list(daily_delta)[-1]]
    else:
        last_eq = 10_000.0 * len(SYMBOLS)
    total["retorno_pct"] = round((last_eq / (10_000.0 * len(SYMBOLS)) - 1) * 100, 2)
    total["periodo_dias"] = len(daily_delta)
    total["sharpe_anual"] = sharpe_from_equity(total["daily"])
    total["max_drawdown_pct"] = max_dd_from_equity(total["daily"])
    total["retorno_pct"] = round(total["pnl_neto"] / (10_000.0 * len(SYMBOLS)) * 100, 2)
    if pw > 0:
        total["win_rate_pct"] = round(pwins / pw * 100, 2)
    if pf_l > 0:
        total["profit_factor"] = round(pf_w / abs(pf_l), 3)
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
def equity_window(symbol: str, window: str, strategy: str = Query("v4")):
    symbol = symbol.upper()
    if window not in ("dia", "semana", "mes", "trimestre", "ano"):
        raise HTTPException(400, "ventana invalida")
    m = _agg_all(strategy) if symbol == "ALL" else _agg(symbol, strategy)
    if "error" in m:
        return {"error": m["error"]}
    return {"symbol": symbol, "window": window, "strategy": _strategy_prefix(strategy), "rows": pnl_by_window(m.get("daily", []), window)}


# ============================================================
# NEW: Wyckoff/SMC Demo Endpoints
# ============================================================
from backtester.structure_analyzer import StructureAnalyzer, analyze_structure_for_backtest
from backtester.session_calculator import SessionCalculator, calculate_session_levels_for_backtest
from backtester.config_loader import get_risk, get_instruments, get_sessions
from backtester.setup_detector import SetupDetector, calculate_atr
from backtester.trigger_engine import TriggerEngine, run_trigger_engine_for_backtest
from backtester.models import Direction, ConfluenceZone, SessionLevel, SessionLevels, SessionName, MarketStructure, SweepEvent, Trend
import pandas as pd
from datetime import datetime, timedelta, timezone


@app.get("/api/candles/{symbol}")
def get_candles(
    symbol: str,
    timeframe: str = Query("15m", description="5m|15m|1h|4h|1d"),
    limit: int = Query(500, ge=100, le=2000),
):
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    tf_map = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1, "4h": Timeframe.H4, "1d": Timeframe.D1}
    tf = tf_map.get(timeframe.lower())
    if not tf:
        raise HTTPException(400, f"timeframe no soportado: {timeframe}")
    data = load_set(symbol, "data/raw")
    if tf not in data:
        raise HTTPException(404, f"sin datos {timeframe} para {symbol}")
    bars = data[tf][-limit:]
    return {"symbol": symbol, "timeframe": timeframe, "count": len(bars), "candles": [{"time": b.time.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars]}

@app.get("/api/demo/wyckoff/{symbol}")
def wyckoff_analysis(
    symbol: str,
    lookback_days: int = Query(30, ge=7, le=180),
    min_sessions: int = Query(2, ge=1, le=3),
    swing_lookback: int = Query(5, ge=3, le=10),
    atr_mult: float = Query(1.5, ge=0.5, le=3.0),
    min_gap_atr: float = Query(0.2, ge=0.05, le=0.5),
    min_bars_acc: int = Query(20, ge=10, le=100),
    vol_lookback: int = Query(20, ge=10, le=50),
    vol_spike: float = Query(1.2, ge=1.0, le=3.0),
    divergence_mult: float = Query(1.5, ge=1.0, le=3.0),
    bars_to_display: int = Query(500, ge=100, le=2000),
    timeframe: str = Query("15m"),
):
    """Análisis Wyckoff multi-timeframe con fases de acumulación/distribución."""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    
    data = load_set(symbol, "data/raw")
    needed = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5]
    missing = [tf.value for tf in needed if tf not in data]
    if missing:
        raise HTTPException(400, f"faltan marcos temporales: {missing}")
    
    # Alinear datos
    m5 = data[Timeframe.M5]
    t0, t1 = m5[0].time, m5[-1].time
    aligned = {tf: [b for b in data[tf] if t0 <= b.time <= t1] for tf in needed}
    
    # Limitar a lookback_days
    cutoff = t1 - timedelta(days=lookback_days)
    aligned = {tf: [b for b in bars if b.time >= cutoff] for tf, bars in aligned.items()}
    
    # Convertir a DataFrames
    daily_candles = [{"timestamp": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in aligned[Timeframe.D1]]
    h4_candles = [{"timestamp": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in aligned[Timeframe.H4]]
    h1_candles = [{"timestamp": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in aligned[Timeframe.H1]]
    m15_candles = [{"timestamp": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in aligned[Timeframe.M15]]
    m5_candles = [{"timestamp": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in aligned[Timeframe.M5]]
    
    daily_df = pd.DataFrame(daily_candles)
    h4_df = pd.DataFrame(h4_candles)
    h1_df = pd.DataFrame(h1_candles)
    m15_df = pd.DataFrame(m15_candles)
    m5_df = pd.DataFrame(m5_candles)
    
    # Detectar estructura macro (D1/H4)
    analyzer = StructureAnalyzer()
    macro = analyzer.analyze_daily_structure(
        # SessionCalculator returns SessionLevels per day, we need to compute them
        # For now, use a simplified approach: extract pivots from daily_df
        _compute_daily_levels_from_df(daily_df),
        daily_df["timestamp"].iloc[-1] if len(daily_df) > 0 else datetime.now(timezone.utc)
    )
    
    # Calcular niveles de sesión para confluencia
    sess_calc = SessionCalculator()
    sessions_cfg = get_sessions()
    session_levels = sess_calc.calculate_daily_levels(m5_df, m5_df["timestamp"].iloc[-1].date())
    
    # Detectar zonas de confluencia
    confluence = sess_calc.detect_confluence_zones(session_levels, symbol)
    
    # Filtrar zonas por min_sessions y dirección macro
    filtered_zones = [
        z for z in confluence 
        if z.strength >= min_sessions
    ]
    
    # Detectar fase Wyckoff en estructura D1
    wyckoff_phase = _detect_wyckoff_phase(daily_df, lookback_days)
    
    # Detección de barridos (sweeps) en M5
    setup_detector = SetupDetector()
    macro_dir = Direction.LONG if macro.trend == Trend.BULLISH else Direction.SHORT
    
    # ATR para validación
    atr_vals = calculate_atr(m5_df, 14)
    
    # Buscar setup zone
    current_price = m5_df["close"].iloc[-1] if len(m5_df) > 0 else 0
    setup_zone = setup_detector.find_setup_zone(filtered_zones, macro.trend.value, current_price)
    
    sweeps = []
    if setup_zone:
        sweeps = setup_detector.scan_for_sweeps(m5_df, [setup_zone], macro_dir, atr_vals)
    
    # Trigger engine para señales
    trigger_engine = TriggerEngine()
    signals = []
    if sweeps:
        signals = run_trigger_engine_for_backtest(
            sweeps, m5_df, symbol, session_levels, macro, filtered_zones, 
            get_risk().risk_reward.sl_pips.get(symbol, 45)
        )
    
    # Volume divergence detection (effort vs result)
    volume_divergence = detect_volume_divergence(m5_df, filtered_zones)
    
    return {
        "symbol": symbol,
        "timeframe_analysis": {
            "macro": {
                "trend": macro.trend.value,
                "bos_levels": [{"price": b.price, "direction": b.direction, "time": b.timestamp.isoformat() if hasattr(b.timestamp, 'isoformat') else str(b.timestamp)} for b in (macro.last_bos if isinstance(macro.last_bos, list) else [macro.last_bos]) if macro.last_bos],
                "choch_levels": [],  # structure_analyzer doesn't separate CHoCH
                "swing_highs": [p.get("high", 0) for p in macro.pivots],
                "swing_lows": [p.get("low", 0) for p in macro.pivots],
            },
            "wyckoff": wyckoff_phase,
            "setup_zone": {
                "price": setup_zone.price if setup_zone else None,
                "is_low": setup_zone.is_low if setup_zone else None,
                "is_high": setup_zone.is_high if setup_zone else None,
                "strength": setup_zone.strength if setup_zone else None,
                "session_count": setup_zone.session_count if hasattr(setup_zone, 'session_count') else setup_zone.strength if setup_zone else None,
                "sessions": setup_zone.sessions if setup_zone else None,
            } if setup_zone else None,
            "confluence_zones": [
                {"price": z.price, "is_low": z.is_low, "is_high": z.is_high, "strength": z.strength, "session_count": z.strength, "sessions": [s.value for s in z.sessions]}
                for z in filtered_zones
            ],
            "detected_sweeps": [
                {
                    "level": s.level,
                    "direction": s.direction.value,
                    "penetration_pips": s.penetration_pips,
                    "wick_ratio": s.wick_ratio,
                    "candles_to_reclaim": s.candles_to_reclaim,
                    "volume_spike": s.volume_spike,
                    "timestamp": s.sweep_candle.get("timestamp", "").isoformat() if isinstance(s.sweep_candle, dict) and "timestamp" in s.sweep_candle else None,
                }
                for s in sweeps
            ],
            "signals": [
                {
                    "direction": sig.direction.value,
                    "entry_price": sig.entry_price,
                    "sl_price": sig.sl_price,
                    "tp_price": sig.tp_price,
                    "sl_pips": sig.sl_pips,
                    "tp_pips": sig.tp_pips,
                    "confidence": sig.confidence,
                    "timestamp": sig.timestamp.isoformat() if hasattr(sig.timestamp, 'isoformat') else str(sig.timestamp),
                    "validation": sig.validation_details,
                }
                for sig in signals
            ],
            "volume_divergence": volume_divergence,
            "session_levels": {
                "london_high": session_levels.london.high,
                "london_low": session_levels.london.low,
                "ny_high": session_levels.newyork.high,
                "ny_low": session_levels.newyork.low,
                "asia_high": session_levels.asia.high,
                "asia_low": session_levels.asia.low,
                "kill_zone_high": session_levels.newyork.high,  # approximate
                "kill_zone_low": session_levels.london.low,  # approximate
            } if session_levels else None,
        }
    }


def _compute_daily_levels_from_df(daily_df: pd.DataFrame):
    """Compute SessionLevels from daily OHLC data for StructureAnalyzer."""
    result = {}
    if len(daily_df) == 0:
        return result
    
    for _, row in daily_df.iterrows():
        date = row["timestamp"]
        high_val = float(row["high"])
        low_val = float(row["low"])
        # Use daily high/low as proxy for session levels
        result[date] = SessionLevels(
            date=date,
            asia=SessionLevel(session=SessionName.ASIA, high=high_val, low=low_val, start_time=date, end_time=date, candle_count=0),
            london=SessionLevel(session=SessionName.LONDON, high=high_val, low=low_val, start_time=date, end_time=date, candle_count=0),
            newyork=SessionLevel(session=SessionName.NEWYORK, high=high_val, low=low_val, start_time=date, end_time=date, candle_count=0),
            timezone="America/Mexico_City"
        )
    return result


def _detect_wyckoff_phase(daily_df: pd.DataFrame, lookback_days: int) -> dict:
    """Detecta fase Wyckoff: Accumulation, Markup, Distribution, Markdown."""
    if len(daily_df) < lookback_days:
        return {"phase": "UNKNOWN", "confidence": 0, "details": "insuficientes datos"}
    
    recent = daily_df.tail(lookback_days).copy()
    recent["range"] = recent["high"] - recent["low"]
    recent["body"] = (recent["close"] - recent["open"]).abs()
    recent["body_ratio"] = recent["body"] / recent["range"]
    
    # Simple phase detection
    # Accumulation: ranging with high volume on down moves
    # Markup: higher highs, higher lows
    # Distribution: ranging with high volume on up moves  
    # Markdown: lower highs, lower lows
    
    closes = recent["close"].values
    highs = recent["high"].values
    lows = recent["low"].values
    
    # Trend detection
    price_change = closes[-1] - closes[0]
    pct_change = price_change / closes[0]
    
    # Range vs trend
    avg_range = recent["range"].mean()
    range_std = recent["range"].std()
    is_ranging = range_std / avg_range < 0.3 if avg_range > 0 else True
    
    if is_ranging and pct_change < 0.02 and pct_change > -0.02:
        # Check volume pattern for accumulation vs distribution
        up_vol = recent[recent["close"] > recent["open"]]["volume"].mean()
        down_vol = recent[recent["close"] < recent["open"]]["volume"].mean()
        if down_vol > up_vol * 1.2:
            return {"phase": "ACCUMULATION", "confidence": 0.7, "details": "Ranging with higher volume on down moves"}
        elif up_vol > down_vol * 1.2:
            return {"phase": "DISTRIBUTION", "confidence": 0.7, "details": "Ranging with higher volume on up moves"}
        return {"phase": "RANGING", "confidence": 0.6, "details": "Neutral ranging"}
    elif pct_change > 0.03:
        return {"phase": "MARKUP", "confidence": 0.8, "details": f"Uptrend {pct_change:.1%}"}
    elif pct_change < -0.03:
        return {"phase": "MARKDOWN", "confidence": 0.8, "details": f"Downtrend {pct_change:.1%}"}
    else:
        return {"phase": "TRANSITION", "confidence": 0.5, "details": "Early trend or consolidation"}


def detect_volume_divergence(m5_df: pd.DataFrame, zones: list) -> dict:
    """Detecta divergencia volumen-precio (esfuerzo vs resultado) estilo Wyckoff."""
    if len(m5_df) < 20:
        return {"divergence_detected": False, "details": "insuficientes datos"}
    
    results = []
    recent = m5_df.tail(50)
    
    for zone in zones:
        zone_price = zone.price
        tolerance = 0.001 * zone_price
        
        # Buscar velas que tocan la zona
        touches = recent[
            (recent["low"] <= zone_price + tolerance) & 
            (recent["high"] >= zone_price - tolerance)
        ]
        
        if len(touches) < 2:
            continue
            
        # Analizar esfuerzo (volumen) vs resultado (movimiento precio)
        for i in range(1, len(touches)):
            prev = touches.iloc[i-1]
            curr = touches.iloc[i]
            
            price_change = abs(curr["close"] - prev["close"])
            volume_change = curr["volume"] / max(prev["volume"], 1)
            
            # Esfuerzo alto (volumen) pero resultado bajo (precio) = divergencia
            if volume_change > 1.5 and price_change < tolerance * 2:
                results.append({
                    "zone_price": zone_price,
                    "type": "absorption" if curr["close"] > prev["close"] else "distribution",
                    "volume_ratio": float(volume_change),
                    "price_change_pips": float(price_change / (0.01 if "XAU" in str(zone_price) else 0.0001)),
                    "timestamp": curr["timestamp"].isoformat() if hasattr(curr["timestamp"], 'isoformat') else str(curr["timestamp"]),
                    "interpretation": "Institutional absorption - possible spring/upthrust"
                })
    
    return {
        "divergence_detected": len(results) > 0,
        "events": results[:10]  # Top 10
    }


@app.get("/api/demo/backtest/custom")
def custom_backtest(
    symbol: str = Query(..., description="Símbolo: EURUSD, GBPUSD, XAUUSD"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    initial_balance: float = Query(10000.0, gt=0),
    risk_pct: float = Query(0.01, gt=0, le=0.1),
    rr_ratio: float = Query(2.0, gt=0, le=10),
    max_concurrent: int = Query(2, ge=1, le=10),
    breakeven_enabled: bool = Query(True),
    partials_enabled: bool = Query(True),
    partial_at_pct: float = Query(40.0, ge=10, le=90),
    partial_close_fraction: float = Query(0.33, ge=0.1, le=0.9),
    kill_switch_daily: float = Query(5.0, ge=1, le=20),
    kill_switch_monthly: float = Query(30.0, ge=5, le=50),
    sl_pips: float = Query(45.0, gt=0, le=200),
    wick_ratio_min: float = Query(0.5, ge=0.1, le=1.0),
    max_penetration_atr: float = Query(1.0, ge=0.1, le=3.0),
    volume_spike_mult: float = Query(1.5, ge=0.5, le=5.0),
    news_guard_enabled: bool = Query(False),  # placeholder
):
    """Backtest personalizado con parámetros ajustables en vivo."""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        raise HTTPException(404, f"simbolo no soportado: {symbol}")
    
    # Cargar datos
    data = load_set(symbol, "data/raw")
    needed = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5]
    missing = [tf.value for tf in needed if tf not in data]
    if missing:
        raise HTTPException(400, f"faltan marcos temporales: {missing}")
    
    m5 = data[Timeframe.M5]
    t0, t1 = m5[0].time, m5[-1].time
    aligned = {tf: [b for b in data[tf] if t0 <= b.time <= t1] for tf in needed}
    
    # Filtrar por fechas
    try:
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "formato fecha invalido (YYYY-MM-DD)")
    aligned = {
        t: [b for b in bars if start_dt <= b.time <= end_dt]
        for t, bars in aligned.items()
    }
    
    # Verificar datos suficientes
    if len(aligned[Timeframe.M5]) < 100:
        raise HTTPException(400, "insuficientes datos M5 en el rango seleccionado")
    
    # Crear RiskConfig personalizado (in-memory, no guarda a YAML)
    from risk.config import RiskConfig, RiskParams
    
    # Use the existing RiskConfig.from_yaml() as base and override
    base_risk = RiskConfig.from_yaml()
    
    # Override with custom params
    custom_risk = RiskConfig(
        params=RiskParams(
            risk_pct=risk_pct,
            rr=rr_ratio,
            max_positions=max_concurrent,
            breakeven_pct=partial_at_pct if breakeven_enabled else 0,
            partials=partial_close_fraction if partials_enabled else 0,
            daily_loss_limit=kill_switch_daily,
            monthly_loss_limit=kill_switch_monthly,
            max_consecutive_losses=5,
        )
    )
    
    # Ejecutar backtest
    bt = MultiTFBacktester(SMCMultiTF(), custom_risk, initial_equity=initial_balance)
    res = bt.run(aligned, Timeframe.M5, drive_range=(start_dt, end_dt))
    
    # Métricas
    m = compute(res.positions, initial_balance, custom_risk)
    m["symbol"] = symbol
    m["daily"] = daily_equity(res)
    m["trades"] = [
        {
            "entry_time": pos.open_time.isoformat() if hasattr(pos.open_time, 'isoformat') else str(pos.open_time),
            "exit_time": pos.close_time.isoformat() if pos.close_time and hasattr(pos.close_time, 'isoformat') else str(pos.close_time) if pos.close_time else None,
            "direction": "LONG" if pos.signal.side.value == "buy" else "SHORT",
            "entry_price": pos.open_price,
            "exit_price": pos.close_price,
            "pnl_usd": pos.pnl(),
            "pnl_pct": pos.pnl() / initial_balance * 100,
            "exit_reason": pos.close_reason,
            "duration_min": int((pos.close_time - pos.open_time).total_seconds() / 60) if pos.close_time and pos.open_time else 0,
            "sl_pips": abs(pos.signal.entry - pos.signal.sl) / (0.01 if symbol == "XAUUSD" else 0.0001),
            "tp_pips": abs(pos.signal.tp - pos.signal.entry) / (0.01 if symbol == "XAUUSD" else 0.0001),
        }
        for pos in res.positions
    ]
    m["rejections"] = dict(collections.Counter(
        x["reason"].split("(")[0].strip() for x in res.rejections
    ))
    
    return m


@app.get("/api/demo/config/defaults")
def demo_config_defaults():
    """Retorna los valores por defecto actuales del config YAML."""
    risk = get_risk()
    inst = get_instruments()
    sess = get_sessions()
    
    return {
        "risk": {
            "risk_pct_per_trade": risk.lot_sizing.risk_pct_per_trade,
            "rr_ratio": risk.risk_reward.ratio,
            "sl_pips": risk.risk_reward.sl_pips,
            "breakeven_enabled": risk.breakeven.enabled,
            "breakeven_trigger_pct": risk.breakeven.trigger_pct_of_tp,
            "partials_enabled": risk.partials.enabled,
            "partial_stages": [{"at_pct": s["at_pct_of_tp"], "close_fraction": s["close_fraction"]} for s in risk.partials.stages],
            "max_concurrent": risk.limits.max_concurrent_trades,
            "max_daily_loss": risk.limits.daily_loss_limit_pct,
            "max_monthly_loss": risk.limits.monthly_loss_limit_pct,
            "max_consecutive_losses": risk.limits.max_consecutive_losses,
            "wick_ratio_min": risk.rejection_validation.min_wick_ratio,
            "max_penetration_atr": risk.rejection_validation.max_penetration_atr,
            "volume_spike_mult": risk.rejection_validation.volume_spike_multiplier,
            "news_guard": risk.session_filters.avoid_high_impact_usd_news,
        },
        "instruments": {
            s: {
                "pip_size": spec.pip_size,
                "pip_value": spec.pip_value_per_lot,
                "spread_pips": spec.spread_typical_pips,
            }
            for s, spec in inst.instruments.items()
        },
        "sessions": {
            "timezone": sess.timezone,
            "sessions": {
                name: {"start": f"{cfg.start_hour:02d}:{cfg.start_minute:02d}", "end": f"{cfg.end_hour:02d}:{cfg.end_minute:02d}"}
                for name, cfg in sess.sessions.items()
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")