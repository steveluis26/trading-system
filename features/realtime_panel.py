"""Panel de contexto en tiempo real (TradingView-style) — CASO A: SOLO LECTURA.
NO toca strategies/ ni risk/. No influye en decisiones de trading.
Calcula 5 metricas por vela M5 desde los datos historicos disponibles:
  1. Tendencia Macro  -> sesgo D1/H4 (misma logica de estructura que la estrategia, pero solo lectura)
  2. Flujo Inmediato (VSA) -> % comprador/vendedor por cierre-dentro-de-rango ponderado por vol
  3. Volumen (5 velas) -> volumen total y relativo vs media movil
  4. Volatilidad (ATR) -> ATR(14) en M5 y regimes (alta/baja)
  5. Liquidez en Radar -> niveles High/Low de sesion no barridos arriba/abajo del precio

VSA es ESTIMACION (no order book real en forex retail). Formula estandar:
  presion = (close - low) / (high - low)  ponderado por volumen de la vela.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from statistics import mean
from core.types import Bar, Timeframe, Side

PIP = 0.0001


def _ema(vals: list[float], period: int) -> float:
    if not vals:
        return 0.0
    k = 2 / (period + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _atr(bars: list[Bar], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, c, pc = bars[i].high, bars[i].low, bars[i].close, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return mean(trs) if trs else 0.0
    return _ema(trs, period)


def _highest_high(bars: list[Bar], n: int) -> float:
    return max(b.high for b in bars[-n:]) if bars else 0.0


def _lowest_low(bars: list[Bar], n: int) -> float:
    return min(b.low for b in bars[-n:]) if bars else 0.0


def _session_levels(m15: list[Bar], sessions_back: int = 6) -> list[tuple[float, str]]:
    """High/Low de las ultimas `sessions_back` velas M15 como niveles de liquidez."""
    out = []
    for b in m15[-sessions_back:]:
        out.append((b.high, "H"))
        out.append((b.low, "L"))
    return out


@dataclass
class PanelSnapshot:
    symbol: str
    time: str
    price: float
    tendencia_macro: str = "—"          # ALCISTA / BAJISTA / LATERAL
    tendencia_detail: str = ""           # texto corto
    flujo_pct_comprador: float = 50.0     # 0-100 estimacion VSA
    flujo_label: str = "EQUILIBRIO"
    volumen_5v: int = 0
    volumen_rel: float = 1.0             # vs media 20 velas
    atr: float = 0.0
    atr_regime: str = "—"
    liquidez_arriba: int = 0             # niveles no barridos sobre precio
    liquidez_abajo: int = 0
    liquidez_detalle: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "time": self.time, "price": round(self.price, 5),
            "tendencia_macro": self.tendencia_macro, "tendencia_detail": self.tendencia_detail,
            "flujo_pct_comprador": round(self.flujo_pct_comprador, 1),
            "flujo_label": self.flujo_label,
            "volumen_5v": self.volumen_5v, "volumen_rel": round(self.volumen_rel, 2),
            "atr": round(self.atr, 5), "atr_regime": self.atr_regime,
            "liquidez_arriba": self.liquidez_arriba, "liquidez_abajo": self.liquidez_abajo,
            "liquidez_detalle": self.liquidez_detalle,
        }


def compute_panel(symbol: str, tf_data: dict[Timeframe, list[Bar]],
                  m5_idx: int | None = None) -> PanelSnapshot:
    """Calcula el snapshot del panel en la vela M5 `m5_idx` (o la ultima)."""
    m5 = tf_data.get(Timeframe.M5, [])
    d1 = tf_data.get(Timeframe.D1, [])
    h4 = tf_data.get(Timeframe.H4, [])
    m15 = tf_data.get(Timeframe.M15, [])
    if not m5:
        return PanelSnapshot(symbol=symbol, time="", price=0.0)

    i = m5_idx if (m5_idx is not None and 0 <= m5_idx < len(m5)) else len(m5) - 1
    cur = m5[i]
    price = cur.close

    # 1) Tendencia Macro: sesgo por estructura D1 + H4 (solo lectura)
    bias = "LATERAL"
    detail = ""
    if len(d1) >= 50:
        ema50 = _ema([b.close for b in d1[-50:]], 50)
        ema200 = _ema([b.close for b in d1[-200:]], 200) if len(d1) >= 200 else ema50
        if price > ema50 > ema200:
            bias = "ALCISTA"
        elif price < ema50 < ema200:
            bias = "BAJISTA"
        detail = f"D1: precio {price:.5f} vs EMA50 {ema50:.5f} vs EMA200 {ema200:.5f}"
    elif len(h4) >= 20:
        hh = _highest_high(h4, 20); ll = _lowest_low(h4, 20)
        if price > hh * 0.999:
            bias = "ALCISTA"
        elif price < ll * 1.001:
            bias = "BAJISTA"
        detail = f"H4: rango {ll:.5f}–{hh:.5f}"

    # 2) Flujo Inmediato (VSA): % comprador por cierre-dentro-de-rango, pond por vol
    win = m5[max(0, i - 19): i + 1]
    if win and all(b.high > b.low for b in win):
        num = sum(((b.close - b.low) / (b.high - b.low)) * (b.volume or 1) for b in win)
        den = sum((b.volume or 1) for b in win)
        pct = (num / den * 100.0) if den else 50.0
    else:
        pct = 50.0
    if pct >= 60:
        flabel = "COMPRA"
    elif pct <= 40:
        flabel = "VENTA"
    else:
        flabel = "EQUILIBRIO"

    # 3) Volumen 5 velas + relativo vs media 20
    w5 = m5[max(0, i - 4): i + 1]
    vol5 = int(sum(b.volume or 0 for b in w5))
    w20 = m5[max(0, i - 19): i + 1]
    vol20 = sum(b.volume or 0 for b in w20)
    vol_rel = (vol5 / 5) / (vol20 / 20) if vol20 else 1.0

    # 4) Volatilidad ATR(14) M5
    atr = _atr(m5[max(0, i - 30): i + 1], 14)
    atr_mean = _atr(m5[max(0, i - 60): i + 1], 14)  # referencia mas larga
    regime = "ALTA" if atr > atr_mean * 1.3 else ("BAJA" if atr < atr_mean * 0.7 else "NORMAL")

    # 5) Liquidez en Radar: niveles M15 no barridos
    levels = _session_levels(m15)
    above = [lv for lv, k in levels if lv > price]
    below = [lv for lv, k in levels if lv < price]
    liq_detail = f"{len(above)} niveles arriba, {len(below)} abajo (sesiones M15 recientes)"

    return PanelSnapshot(
        symbol=symbol, time=cur.time.strftime("%Y-%m-%d %H:%M UTC"),
        price=price, tendencia_macro=bias, tendencia_detail=detail,
        flujo_pct_comprador=pct, flujo_label=flabel,
        volumen_5v=vol5, volumen_rel=vol_rel,
        atr=atr, atr_regime=regime,
        liquidez_arriba=len(above), liquidez_abajo=len(below), liquidez_detalle=liq_detail,
    )
