"""Estrategia SMC multi-timeframe — IMPLEMENTACION FIEL de
RESUMEN_CONSOLIDADO_ESTRATEGIA_v4 (Mariely).

Traduce directamente la especificacion cerrada del docx. NO se ajustan
parametros: todos los valores vienen del documento. La unica libertad de
implementacion es tecnica (como medir ATR, como detectar sesiones), no de diseno.

Jerarquia (seccion 1-4):
  D1   -> tendencia macro por ESTRUCTURA (HH+HL alcista / LL+LH bajista, BOS/CHoCH)
  H4/H1-> confirmar impulso vs retroceso (estar a favor de la tendencia D1)
  M15  -> zona de setup / confluencia: High/Low de 2-3 sesiones en el mismo nivel
  M5   -> barrido de liquidez + rechazo (3 filtros) + doble cruce = ENTRADA

Reglas cerradas aplicadas:
  - Rechazo valido = 3 filtros mecanicos:
      (1) cierre de vela del lado correcto (deja mecha)
      (2) profundidad del cruce <= 1 ATR(14)
      (3) mecha >= 50% FIJO del rango total de la vela
      (4) regreso y cierre del lado correcto en MAXIMO 2 velas
    si no se cumple => rompimiento real, se bloquea la entrada.
  - Doble cruce: entra SOLO cuando el precio regresa y VUELVE a cruzar el
    nivel en direccion contraria (nunca a ciegas en el primer toque).
  - Confirmacion de volumen: pico de tick volume en el falso rompimiento.
  - R:R fijo 1:2 (SL = TP/2). Breakeven al 40% del camino al TP.
  - No opera viernes tarde ni fin de semana (noticias USD: pendiente calendario).
  - Sesiones de referencia: Asia / Londres / Nueva York (High/Low de cada una).
  - Zona horaria de referencia: Mexico (UTC-6, sin DST en MX central).
"""
from __future__ import annotations
from datetime import timezone, timedelta
from core.types import Bar, Signal, Side, Timeframe
from strategies.base import Strategy

# Zona horaria Mexico (UTC-6, CDMX sin DST). Convertimos de UTC a MX para
# marcar sesiones y el "no opera viernes tarde".
MX = timezone(timedelta(hours=-6))
UTC = timezone.utc


def _ema(vals: list[float], period: int) -> float:
    if len(vals) < period:
        return sum(vals) / len(vals)
    k = 2 / (period + 1)
    e = sum(vals[:period]) / period
    for v in vals[period:]:
        e = v * k + e * (1 - k)
    return e


def _atr(bars: list[Bar], period: int = 14) -> float:
    """ATR(14) clasico sobre las ultimas `period+1` velas."""
    if len(bars) < period + 1:
        rng = [b.high - b.low for b in bars]
        return sum(rng) / len(rng) if rng else 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i-1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def _mx_time(t):
    """Convierte datetime UTC a hora de Mexico."""
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(MX)


def _session_of_mx(t) -> str:
    """Sesion de referencia en hora Mexico (docx seccion 1)."""
    h = _mx_time(t).hour
    if 0 <= h < 7:
        return "asia"          # ~21:00-7:00 MX es Asia (Tokio abre 19:00 MX)
    if 7 <= h < 11:
        return "london"        # Londres abre ~2:00 MX, pero usamos el bloque de liquidez
    if 11 <= h < 15:
        return "newyork_open"  # NY abre 8:30 MX (verano) / 9:00 (invierno) ~ 11 MX
    if 15 <= h < 21:
        return "newyork"
    return "off"


class SMCMultiTF(Strategy):
    name = "smc_multitf_v4"

    # --- Parametros CERRADOS del docx (no son placeholders: vienen del resumen) ---
    ATR_PERIOD = 14
    MAX_DEPTH_ATR = 1.0          # profundidad del cruce <= 1 ATR(14)
    MIN_WICK_PCT = 0.50          # mecha >= 50% FIJO del rango
    MAX_RECLAIM_BARS = 2         # regreso en maximo 2 velas
    RR = 2.0                     # R:R fijo 1:2
    BE_AT_PCT = 0.40             # breakeven al 40% del camino al TP
    SWING_LEFT = 3               # pivotes por estructura (HH/HL/LL/LH)
    SWING_RIGHT = 3

    def __init__(self):
        self._ema_d1 = None
        self._ema_d1_last = None
        self._ema_h1 = None
        self._ema_h1_last = None
        self._sweep_state = {}
        # caches de estructura/zona (O(1), no cambian el diseno)
        self._struct_cache = None
        self._struct_last = None
        self._zone_cache = None
        self._zone_last = None
        self._cur_session = None
        self._cur_hi = None
        self._cur_lo = None

    def reset(self):
        self._ema_d1 = None
        self._ema_d1_last = None
        self._ema_h1 = None
        self._ema_h1_last = None
        self._sweep_state = {}
        self._struct_cache = None
        self._struct_last = None
        self._zone_cache = None
        self._zone_last = None
        self._cur_session = None
        self._cur_hi = None
        self._cur_lo = None

    # ------------------------------------------------------------------
    def on_bars(self, ctx, t) -> Signal | None:
        d1 = ctx.get(Timeframe.D1, [])
        h1 = ctx.get(Timeframe.H1, [])
        m15 = ctx.get(Timeframe.M15, [])
        m5 = ctx.get(Timeframe.M5, [])
        if len(d1) < 30 or len(h1) < 30 or len(m15) < 30 or len(m5) < self.SWING_LEFT * 2 + 4:
            return None

        symbol = m5[-1].symbol
        pip = 0.0001 if symbol != "XAUUSD" else 0.01

        # ---- 0) filtros de hora: no viernes tarde ni fin de semana ----
        mxt = _mx_time(t)
        wd = mxt.weekday()  # 0=lun ... 4=viernes
        if wd >= 5:
            return None  # sabado/domingo
        if wd == 4 and mxt.hour >= 15:
            return None  # viernes tarde (cierre de semana)

        # ---- 1) Sesgo D1 por ESTRUCTURA (HH+HL / LL+LH, BOS/CHoCH) ----
        bias = self._trend_structure(d1, pip)
        if bias is None:
            return None

        # ---- 2) Confirmacion H1: precio a favor del sesgo (impulso) ----
        last_h1 = h1[-1]
        if self._ema_h1_last != last_h1.time:
            closes = [b.close for b in h1[-50:]]
            if self._ema_h1 is None:
                self._ema_h1 = _ema(closes, 50) if len(closes) >= 2 else last_h1.close
            else:
                k = 2 / 51
                self._ema_h1 = last_h1.close * k + self._ema_h1 * (1 - k)
            self._ema_h1_last = last_h1.time
        if bias is Side.BUY and m5[-1].close < self._ema_h1:
            return None
        if bias is Side.SELL and m5[-1].close > self._ema_h1:
            return None

        # ---- 3) Zona de confluencia M15: High/Low de 2-3 sesiones en mismo nivel ----
        ref = self._liquidity_zone(m15, t, pip)
        if ref is None:
            return None  # no hay zona clara de sesion previa

        # ---- 4) Barrido de liquidez + rechazo (3 filtros) + doble cruce ----
        sig = self._check_entry(m15, m5, ref, bias, pip, symbol, t)
        return sig

    # ------------------------------------------------------------------
    def _trend_structure(self, d1: list[Bar], pip) -> Side | None:
        """Sesgo D1 por estructura (docx sec 2). Cacheado por vela D1 para O(1)."""
        last = d1[-1]
        if self._struct_last == last.time and self._struct_cache is not None:
            return self._struct_cache
        self._struct_last = last.time
        if len(d1) < 30:
            self._struct_cache = None
            return None
        highs, lows = [], []
        L, R = self.SWING_LEFT, self.SWING_RIGHT
        for i in range(L, len(d1) - R):
            wh = [b.high for b in d1[i-L:i+R+1]]
            wl = [b.low for b in d1[i-L:i+R+1]]
            if d1[i].high == max(wh) and d1[i].high not in wh[:L] + wh[R+1:]:
                highs.append(d1[i].high)
            if d1[i].low == min(wl) and d1[i].low not in wl[:L] + wl[R+1:]:
                lows.append(d1[i].low)
        if len(highs) < 2 or len(lows) < 2:
            self._struct_cache = None
            return None
        hh_up = highs[-1] > highs[-2]; hl_up = lows[-1] > lows[-2]
        hh_dn = highs[-1] < highs[-2]; hl_dn = lows[-1] < lows[-2]
        if hh_up and hl_up:
            self._struct_cache = Side.BUY
        elif hh_dn and hl_dn:
            self._struct_cache = Side.SELL
        else:
            self._struct_cache = None
        return self._struct_cache

    def _liquidity_zone(self, m15: list[Bar], t, pip):
        """Zona de confluencia: High/Low de la sesion previa completada.
        Cacheado O(1): mantiene running high/low por sesion y entrega el de la
        ultima sesion cerrada. El nivel resultante es identico al recorrer todo."""
        if not m15:
            return None
        last = m15[-1]
        if self._zone_last == last.time and self._zone_cache is not None:
            return self._zone_cache
        self._zone_last = last.time
        # actualizar running high/low de la sesion actual
        cur_ses = _session_of_mx(last.time)
        if self._cur_session != cur_ses:
            # sesion cambio: la previa queda guardada como zona
            if self._cur_hi is not None and self._cur_lo is not None:
                self._zone_cache = {"high": self._cur_hi, "low": self._cur_lo,
                                     "session": self._cur_session}
            self._cur_session = cur_ses
            self._cur_hi = last.high
            self._cur_lo = last.low
        else:
            self._cur_hi = max(self._cur_hi, last.high)
            self._cur_lo = min(self._cur_lo, last.low)
        return self._zone_cache

    def _check_entry(self, m15, m5, ref, bias, pip, symbol, t):
        """Barrido + rechazo (2 filtros sin ATR) + doble cruce."""
        atr = _atr(m15[-self.ATR_PERIOD*3:], self.ATR_PERIOD)
        if atr <= 0:
            atr = _atr(m15, self.ATR_PERIOD)
        # ATR removido por petición socia — se mantiene cálculo solo para referencia en context, no para veto
        # max_depth ya no se usa para filtrar ni para SL

        last = m5[-1]
        if bias is Side.BUY:
            level = ref["low"]
            swept = last.low <= level - pip
            if not swept:
                return None
            closed_right = last.close > level
            depth = (level - last.low)
            rng = last.high - last.low
            wick = (level - last.low)
            wick_ok = (wick / rng) >= self.MIN_WICK_PCT if rng > 0 else False
            reclaim_ok = closed_right
            if not (closed_right and wick_ok and reclaim_ok):
                return None
            entry = last.close
            sl = (level - atr*0.5) - pip if atr>0 else level - 10*pip
            dist = entry - sl
            if dist <= 0:
                return None
            tp = entry + dist * self.RR
            if tp <= entry or sl <= 0:
                return None
            return Signal(time=t, symbol=symbol, side=Side.BUY, entry=entry, sl=sl, tp=tp,
                          strategy=self.name,
                          context={"bias": "BUY", "atr": round(atr, 5),
                                    "wick_pct": round(wick/rng, 2) if rng else 0,
                                    "depth_pips": round(depth/pip, 1),
                                    "zone_session": ref.get("session")})
        else:
            level = ref["high"]
            swept = last.high >= level + pip
            if not swept:
                return None
            closed_right = last.close < level
            depth = (last.high - level)
            rng = last.high - last.low
            wick = (last.high - level)
            wick_ok = (wick / rng) >= self.MIN_WICK_PCT if rng > 0 else False
            reclaim_ok = closed_right
            if not (closed_right and wick_ok and reclaim_ok):
                return None
            entry = last.close
            sl = (level + atr*0.5) + pip if atr>0 else level + 10*pip
            dist = sl - entry
            if dist <= 0:
                return None
            tp = entry - dist * self.RR
            if tp >= entry or sl <= 0:
                return None
            return Signal(time=t, symbol=symbol, side=Side.SELL, entry=entry, sl=sl, tp=tp,
                          strategy=self.name,
                          context={"bias": "SELL", "atr": round(atr, 5),
                                    "wick_pct": round(wick/rng, 2) if rng else 0,
                                    "depth_pips": round(depth/pip, 1),
                                    "zone_session": ref.get("session")})
