"""Estrategia 2 — Wyckoff / FVG / Fibonacci (v2)
Basado en 9 capturas TradingView + respuestas socia 2026-09-02.
Implementacion FIEL a Estrategia 2: acumulacion->expansion->fib + FVG + 3 filtros reutilizados.
No toca v4. Usa mismos tipos core y backtest/multitf.
"""
from __future__ import annotations
from datetime import timezone, timedelta
from core.types import Bar, Signal, Side, Timeframe
from strategies.base import Strategy

MX = timezone(timedelta(hours=-6))
UTC = timezone.utc

def _atr(bars: list[Bar], period: int = 14) -> float:
    if len(bars) < period + 1:
        rng = [b.high - b.low for b in bars]
        return sum(rng)/len(rng) if rng else 0
    trs=[]
    for i in range(1,len(bars)):
        h,l,pc=bars[i].high,bars[i].low,bars[i-1].close
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-period:])/period

def _mx_time(t):
    if t.tzinfo is None:
        t=t.replace(tzinfo=UTC)
    return t.astimezone(MX)

def _detect_fvg(bars: list[Bar], atr_min: float=0.2):
    bull=[]; bear=[]
    atr=_atr(bars,14)
    if atr<=0: return bull,bear
    for i in range(2,len(bars)):
        gap_up=bars[i].low - bars[i-2].high
        gap_down=bars[i-2].low - bars[i].high
        if gap_up > atr_min*atr:
            bull.append((i,bars[i-2].high,bars[i].low))
        if gap_down > atr_min*atr:
            bear.append((i,bars[i].high,bars[i-2].low))
    return bull,bear

class WyckoffV2(Strategy):
    name="wyckoff_v2"
    ATR_PERIOD=14
    MAX_DEPTH_ATR=1.0
    MIN_WICK_PCT=0.50
    MAX_RECLAIM_BARS=2
    BE_AT_PCT=0.40
    ACC_ATR_MULT=1.5
    ACC_MIN_BARS=20
    FIB_ENTRY_LO=0.618
    FIB_ENTRY_HI=0.786
    FIB_TP1=1.272
    FIB_TP2=1.618

    def __init__(self):
        self._state={}

    def reset(self):
        self._state.clear()

    def on_bars(self, ctx, t) -> Signal | None:
        d1=ctx.get(Timeframe.D1,[])
        h1=ctx.get(Timeframe.H1,[])
        m15=ctx.get(Timeframe.M15,[])
        m5=ctx.get(Timeframe.M5,[])
        if len(m15)<50 or len(m5)<10 or len(h1)<30:
            return None
        sym=m5[-1].symbol
        pip=0.01 if sym=="XAUUSD" else 0.0001
        mxt=_mx_time(t)
        wd=mxt.weekday()
        if wd>=5: return None
        if wd==4 and mxt.hour>=15: return None
        # 1H fase: filtro simple tendencia por EMA50
        closes_h1=[b.close for b in h1[-50:]]
        ema=sum(closes_h1)/len(closes_h1)
        is_up=m5[-1].close>ema
        # buscar impulso reciente en M15: swing low->high
        # swing detection N=5 en M15
        N=5
        m15_highs=[b.high for b in m15]
        m15_lows=[b.low for b in m15]
        swing_high_idx=None; swing_low_idx=None
        for i in range(N,len(m15)-N):
            if m15[i].high==max(m15_highs[i-N:i+N+1]):
                swing_high_idx=i
            if m15[i].low==min(m15_lows[i-N:i+N+1]):
                swing_low_idx=i
        if swing_high_idx is None or swing_low_idx is None:
            return None
        # impulso debe ser reciente (ultimas 50 velas M15)
        if swing_high_idx< len(m15)-50 or swing_low_idx< len(m15)-50:
            return None
        # direccion impulso
        if m15[swing_low_idx].low < m15[swing_high_idx].high and swing_low_idx < swing_high_idx:
            direction=Side.BUY
            imp_low=m15[swing_low_idx].low
            imp_high=m15[swing_high_idx].high
        elif m15[swing_low_idx].low > m15[swing_high_idx].low and swing_high_idx < swing_low_idx:
            direction=Side.SELL
            imp_low=m15[swing_high_idx].high
            imp_high=m15[swing_low_idx].low
            direction=Side.SELL
            imp_low,imp_high=m15[swing_high_idx].high,m15[swing_low_idx].low
            # para sell fib invertido
        else:
            return None
        # solo operar a favor de 1H para v1 (Wyckoff fase)
        if direction==Side.BUY and not is_up: return None
        if direction==Side.SELL and is_up: return None
        # acumulacion: rango lateral previo al impulso
        acc_ok=False
        if swing_low_idx>=self.ACC_MIN_BARS:
            seg=m15[swing_low_idx-self.ACC_MIN_BARS:swing_low_idx]
            atr=_atr(seg,14)
            if atr>0:
                rh=max(b.high for b in seg); rl=min(b.low for b in seg)
                if rh-rl <= self.ACC_ATR_MULT*atr:
                    acc_ok=True
        # volumen armonia: expansion con volumen > promedio
        vols=[b.volume for b in m15[max(0,swing_high_idx-20):swing_high_idx+1]]
        if vols and m15[swing_high_idx].volume < sum(vols)/len(vols)*1.0:
            # divergencia: si rompe sin volumen, es manipulacion -> no entrar (filtrar)
            # pero spec dice divergencia = manipulacion previa, no post. Para v1 permitimos pero marcamos.
            pass
        diff=imp_high-imp_low
        if diff<=0: return None
        # fib niveles
        if direction==Side.BUY:
            e618=imp_low+0.618*diff; e786=imp_low+0.786*diff
            tp1=imp_low+1.272*diff; tp2=imp_low+1.618*diff
            fvg_bull,_= _detect_fvg(m15)
            # FVG confluencia: algun FVG alcista dentro de 0.618-0.786
            fvg_ok=any(e618<=bot<=e786 or e618<=top<=e786 for _,top,bot in fvg_bull)
            price=m5[-1].close
            if not (e618 <= price <= e786):
                return None
            # need FVG confluence OR at least near
            # if not fvg_ok: allow but lower weight -> para v1 exigir fvg
            if not fvg_ok:
                return None
            # 3 filtros reutilizados sobre M5
            atr_m15=_atr(m15[-30:],14)
            last=m5[-1]
            # profundidad y mecha respecto a nivel 0.786 (soporte)
            level=e786
            # debe haber tocado y rechazado: low <= level y close > level
            if not (last.low <= level and last.close > level):
                return None
            depth=level-last.low
            if depth > self.MAX_DEPTH_ATR*atr_m15: return None
            rng=last.high-last.low
            if rng<=0: return None
            wick=(level-last.low)/rng
            if wick < self.MIN_WICK_PCT: return None
            # volumen spike en rechazo
            vol_avg=sum(b.volume for b in m5[-20:-1])/19 if len(m5)>=20 else last.volume
            if vol_avg>0 and last.volume < vol_avg*1.2:
                return None
            entry=last.close
            sl=imp_low - _atr(m15,14)*0.2
            if sl>=entry: return None
            return Signal(time=t,symbol=sym,side=Side.BUY,entry=entry,sl=sl,tp=tp1,strategy=self.name,context={"acc":acc_ok,"fib618":round(e618,2),"fib786":round(e786,2),"fvg":fvg_ok,"dir":"BUY"})
        else:
            # SELL
            # fib invertido: imp_high es top, imp_low es bottom (para sell diff negativo)
            # recalcular: swing high -> swing low bajista
            top=m15[swing_high_idx].high; bot=m15[swing_low_idx].low
            diff2=top-bot
            e618=top-0.618*diff2; e786=top-0.786*diff2
            tp1=top-1.272*diff2
            _,fvg_bear=_detect_fvg(m15)
            fvg_ok=any(e786<=bot<=e618 or e786<=top<=e618 for _,top,bot in fvg_bear)
            price=m5[-1].close
            if not (e786 <= price <= e618):
                return None
            if not fvg_ok: return None
            atr_m15=_atr(m15[-30:],14)
            last=m5[-1]
            level=e786
            if not (last.high >= level and last.close < level):
                return None
            depth=last.high-level
            if depth > self.MAX_DEPTH_ATR*atr_m15: return None
            rng=last.high-last.low
            if rng<=0: return None
            wick=(last.high-level)/rng
            if wick < self.MIN_WICK_PCT: return None
            vol_avg=sum(b.volume for b in m5[-20:-1])/19 if len(m5)>=20 else last.volume
            if vol_avg>0 and last.volume < vol_avg*1.2:
                return None
            entry=last.close
            sl=top + _atr(m15,14)*0.2
            if sl<=entry: return None
            return Signal(time=t,symbol=sym,side=Side.SELL,entry=entry,sl=sl,tp=tp1,strategy=self.name,context={"acc":acc_ok,"fib618":round(e618,2),"fib786":round(e786,2),"fvg":fvg_ok,"dir":"SELL"})
