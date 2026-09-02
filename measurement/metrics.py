"""Metricas de performance. Todo NETO de costos.
Accuracy y AUC son irrelevantes aqui: lo que importa es dinero ajustado por riesgo.
"""
from __future__ import annotations
import math
from core.types import Position

def _streak(flags) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best

def compute(positions: list[Position], initial: float = 10_000.0,
            cfg=None) -> dict:
    if not positions:
        return {"n_trades": 0, "veredicto": "SIN OPERACIONES"}
    # P&L por posicion usando su propio simbolo (oro=1 USD/pip, forex=10 USD/pip)
    pnl = []
    for p in positions:
        sym = p.signal.symbol
        upp = cfg.usd_per_pip(sym) if cfg else 10.0
        pip = cfg.pip(sym) if cfg else 0.0001
        pnl.append(p.pnl(upp, pip))
    wins = [x for x in pnl if x > 0]; losses = [x for x in pnl if x < 0]
    gw, gl = sum(wins), abs(sum(losses))

    eq, peak, dd = initial, initial, 0.0
    for x in pnl:
        eq += x; peak = max(peak, eq); dd = max(dd, (peak - eq) / peak * 100)

    days = max((positions[-1].close_time - positions[0].open_time).days, 1)
    tpy = len(pnl) / days * 365
    r = [x / initial for x in pnl]
    mu = sum(r) / len(r)
    sd = math.sqrt(sum((x-mu)**2 for x in r) / len(r)) if len(r) > 1 else 0
    neg = [x for x in r if x < 0]
    dsd = math.sqrt(sum(x*x for x in neg)/len(neg)) if neg else 0
    sharpe = mu/sd*math.sqrt(tpy) if sd else None
    sortino = mu/dsd*math.sqrt(tpy) if dsd else None

    m = {
        "n_trades": len(pnl),
        "periodo_dias": days,
        "trades_por_dia": round(len(pnl)/days, 2),
        "pnl_neto": round(sum(pnl), 2),
        "retorno_pct": round(sum(pnl)/initial*100, 2),
        "win_rate_pct": round(len(wins)/len(pnl)*100, 2),
        "profit_factor": round(gw/gl, 3) if gl else float("inf"),
        "expectancy": round(sum(pnl)/len(pnl), 4),
        "payoff_ratio": round((sum(wins)/len(wins))/abs(sum(losses)/len(losses)), 3)
                        if wins and losses else None,
        "max_drawdown_pct": round(dd, 2),
        "sharpe_anual": round(sharpe, 3) if sharpe else None,
        "sortino_anual": round(sortino, 3) if sortino else None,
        "costos_totales": round(sum(p.commission + p.swap for p in positions), 2),
        "gross_profit": round(gw, 2),
        "gross_loss": round(gl, 2),
        "max_perdidas_consecutivas": _streak(x < 0 for x in pnl),
        "salidas": {k: sum(1 for p in positions if p.close_reason.startswith(k))
                    for k in ("tp","sl","end_of_data")},
    }
    m["veredicto"] = verdict(m)
    return m

CRITERIOS = dict(sharpe_min=1.0, dd_max_pct=15.0, pf_min=1.2, min_trades=100, min_days=250)

def verdict(m: dict) -> str:
    if m["n_trades"] < CRITERIOS["min_trades"]:
        return f"INSUFICIENTE: {m['n_trades']} trades (<{CRITERIOS['min_trades']}). Ruido, no evidencia."
    if m["periodo_dias"] < CRITERIOS["min_days"]:
        return f"INSUFICIENTE: {m['periodo_dias']} dias (<{CRITERIOS['min_days']}). Ventana corta, no vio regímenes."
    f = []
    if (m["sharpe_anual"] or -9) < CRITERIOS["sharpe_min"]: f.append(f"Sharpe {m['sharpe_anual']}<1.0")
    if m["max_drawdown_pct"] > CRITERIOS["dd_max_pct"]:     f.append(f"DD {m['max_drawdown_pct']}%>15%")
    if m["profit_factor"] < CRITERIOS["pf_min"]:            f.append(f"PF {m['profit_factor']}<1.2")
    if m["expectancy"] <= 0:                                f.append(f"Expectancy {m['expectancy']}<=0")
    if f:
        return "SIN EDGE -> " + "; ".join(f)
    # incluso cumpliendo los 4, con <200 trades es PROMETEDOR no confirmado
    if m["n_trades"] < 200:
        return "PROMETEDOR (cumple 4 criterios pero muestra corta: <200 trades, requiere walk-forward out-of-sample)"
    return "EDGE PLAUSIBLE (cumple 4 criterios + muestra robusta)"


def daily_equity(res) -> list:
    """Curva de equity por DIA desde res.equity (lista de (datetime, equity)).
    Devuelve [(fecha_str, equity)] con el ultimo equity de cada dia."""
    from collections import OrderedDict
    by_day = OrderedDict()
    for t, eq in res.equity:
        by_day[t.strftime("%Y-%m-%d")] = eq
    return [(k, v) for k, v in by_day.items()]


def sharpe_from_equity(daily: list, initial: float = 10_000.0) -> float:
    """Sharpe anualizado desde curva de equity diaria."""
    if len(daily) < 30:
        return 0.0
    rets = []
    prev = initial
    for _, eq in daily:
        if prev > 0:
            rets.append((eq - prev) / prev)
        prev = eq
    import math
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / max(len(rets) - 1, 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    # anualizar asumiendo ~252 dias de trading
    sharpe = (mu / sd) * math.sqrt(252)
    return round(sharpe, 3)


def max_dd_from_equity(daily: list, initial: float = None) -> float:
    """Max drawdown % desde curva de equity diaria. Si initial=None usa el
    primer equity como peak base (para cuentas combinadas cuyo arranque no es 10000)."""
    if not daily:
        return 0.0
    peak = daily[0][1] if initial is None else initial
    mdd = 0.0
    for _, eq in daily:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak * 100)
    return round(mdd, 2)


def pnl_by_window(daily, window, initial=10_000.0):
    """Agrega la curva diaria por ventana: dia | semana | mes | trimestre | ano.
    Devuelve lista de {label, equity_final, pnl, retorno_pct}."""
    import datetime as _dt
    if not daily:
        return []
    def key_of(date_str, w):
        d = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        if w == "dia":
            return date_str
        if w == "semana":
            dmon = d - _dt.timedelta(days=d.weekday())
            return dmon.strftime("%Y-%m-%d")
        if w == "mes":
            return d.strftime("%Y-%m")
        if w == "trimestre":
            return f"{d.year}-Q{(d.month - 1)//3 + 1}"
        if w == "ano":
            return d.strftime("%Y")
        return date_str
    ordered = sorted({key_of(d, window) for d, _ in daily})
    out = []
    for k in ordered:
        eqs = [v for d, v in daily if key_of(d, window) == k]
        out.append({
            "label": k,
            "equity_final": round(eqs[-1], 2),
            "pnl": round(eqs[-1] - initial, 2),
            "retorno_pct": round((eqs[-1] / initial - 1) * 100, 2),
        })
    return out
