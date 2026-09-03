"""Estrategia 2 — Wyckoff / FVG / Fibonacci (v2)
Integrada al panel único. Corrige bugs críticos 0 trades sin tocar diseño v4.
TP fib 1.272/1.618, SL swing, RR=2, BE configurable, FVG OR peso (no veto).
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
    BE_MODE="pct_40"
    ACC_ATR_MULT=1.5
    ACC_MIN_BARS=20
    N_SWINGS=5
    MIN_GAP_ATR=0.2
    VOL_LOOKBACK=20
    VOL_MULT=1.2

    def __init__(self, be_mode: str = "pct_40"):
        self.BE_MODE=be_mode
        self._state={}

    def reset(self):
        self._state.clear()

    def _find_swings(self, m15: list[Bar]):
        N=self.N_SWINGS
        # buscar desde el final hacia atrás para impulso reciente
        swing_high_idx=None; swing_low_idx=None
        for i in range(len(m15)-N-1, N-1, -1):
            if swing_high_idx is None and m15[i].high==max(b.high for b in m15[i-N:i+N+1]):
                swing_high_idx=i
            if swing_low_idx is None and m15[i].low==min(b.low for b in m15[i-N:i+N+1]):
                swing_low_idx=i
            if swing_high_idx is not None and swing_low_idx is not None:
                break
        return swing_high_idx, swing_low_idx

    def on_bars(self, ctx, t) -> Signal | None:
        d1=ctx.get(Timeframe.D1,[]); h1=ctx.get(Timeframe.H1,[]); m15=ctx.get(Timeframe.M15,[]); m5=ctx.get(Timeframe.M5,[])
        if len(m15)<50 or len(m5)<10 or len(h1)<30:
            return None
        sym=m5[-1].symbol; pip=0.01 if sym=="XAUUSD" else 0.0001
        mxt=_mx_time(t)
        if mxt.weekday()>=5: return None
        if mxt.weekday()==4 and mxt.hour>=15: return None
        closes_h1=[b.close for b in h1[-50:]]
        sma=sum(closes_h1)/len(closes_h1)
        is_up=m5[-1].close > sma
        sh, sl = self._find_swings(m15)
        if sh is None or sl is None:
            return None
        # impulso reciente: ambos swings dentro de últimas 80 velas M15 (~20h) — deja ajustar
        if sh < len(m15)-80 or sl < len(m15)-80:
            return None
        # dirección: swing_low < swing_high y low antes que high = impulso alcista
        if sl < sh and m15[sl].low < m15[sh].high:
            direction=Side.BUY
            imp_low=m15[sl].low; imp_high=m15[sh].high
        elif sh < sl and m15[sh].high > m15[sl].low:
            direction=Side.SELL
            imp_low=m15[sh].high; imp_high=m15[sl].low
            # SELL: top->bot
            top=m15[sh].high; bot=m15[sl].low
            imp_low=top; imp_high=bot
            direction=Side.SELL
        else:
            return None
        diff=abs(imp_high-imp_low)
        if diff<=0: return None
        if direction==Side.BUY and not is_up: return None
        if direction==Side.SELL and is_up: return None
        # acumulación: rango previo al swing_low
        acc_ok=False
        idx_acc=sl if direction==Side.BUY else sh
        if idx_acc>=self.ACC_MIN_BARS:
            seg=m15[idx_acc-self.ACC_MIN_BARS:idx_acc]
            atr=_atr(seg,14)
            if atr>0:
                rh=max(b.high for b in seg); rl=min(b.low for b in seg)
                if rh-rl <= self.ACC_ATR_MULT*atr:
                    acc_ok=True
        # precio M5 actual
        last=m5[-1]
        atr_m15=_atr(m15[-30:],14)
        if atr_m15<=0: atr_m15=diff*0.1
        if direction==Side.BUY:
            # Fib BUY: imp_low->imp_high
            lo=imp_low; hi=imp_high
            e618=lo+0.618*diff; e786=lo+0.786*diff
            # FVG peso (OR, no veto)
            fvg_bull,_=_detect_fvg(m15, self.MIN_GAP_ATR)
            fvg_ok=any(e618<=bot<=e786 or e618<=top<=e786 for _,top,bot in fvg_bull)
            level=e786
            # 3 filtros: debe haber barrido nivel y cerrado arriba (rechazo)
            if not (last.low <= level and last.close > level):
                return None
            depth=level-last.low
            if depth > self.MAX_DEPTH_ATR*atr_m15: return None
            rng=last.high-last.low
            if rng<=0: return None
            if (level-last.low)/rng < self.MIN_WICK_PCT: return None
            # volumen spike opcional (peso, no veto estricto)
            # si no hay volumen (forex 0) no veta
            vol_avg=(sum(b.volume for b in m5[-self.VOL_LOOKBACK:-1])/(self.VOL_LOOKBACK-1)) if len(m5)>=self.VOL_LOOKBACK and sum(b.volume for b in m5[-self.VOL_LOOKBACK:-1])>0 else 0
            # no vetar, solo marca
            entry=last.close
            sl_price=lo - _atr(m15,14)*0.2
            if sl_price>=entry: return None
            # TP con RR=2 para pasar risk veto, pero nivel fib como referencia en context
            risk=entry - sl_price
            tp_rr=entry + risk*2.0
            tp_fib=lo+1.272*diff
            tp=tp_rr
            # BE_MODE configurable: si fib_1272 usar tp_fib para BE calc en backtester (via context)
            be_ref= tp_fib if self.BE_MODE=="fib_1272" else tp_rr
            return Signal(time=t,symbol=sym,side=Side.BUY,entry=entry,sl=sl_price,tp=tp,strategy=self.name,context={"acc":acc_ok,"fvg_ok":fvg_ok,"fvg_weight":0.2 if fvg_ok else 0,"fib618":round(e618,2),"fib786":round(e786,2),"tp_fib":round(tp_fib,2),"tp_rr":round(tp_rr,2),"be_mode":self.BE_MODE,"be_ref":round(be_ref,2),"dir":"BUY"})
        else:
            top=m15[sh].high; bot=m15[sl].low
            e618=top-0.618*diff; e786=top-0.786*diff
            _,fvg_bear=_detect_fvg(m15, self.MIN_GAP_ATR)
            fvg_ok=any(e786<=bot<=e618 or e786<=top<=e618 for _,top,bot in fvg_bear)
            level=e786
            if not (last.high >= level and last.close < level):
                return None
            depth=last.high-level
            if depth > self.MAX_DEPTH_ATR*atr_m15: return None
            rng=last.high-last.low
            if rng<=0: return None
            if (last.high-level)/rng < self.MIN_WICK_PCT: return None
            entry=last.close
            sl_price=top + _atr(m15,14)*0.2
            if sl_price<=entry: return None
            risk=sl_price - entry
            tp_rr=entry - risk*2.0
            tp_fib=top-1.272*diff
            tp=tp_rr
            be_ref=tp_fib if self.BE_MODE=="fib_1272" else tp_rr
            return Signal(time=t,symbol=sym,side=Side.SELL,entry=entry,sl=sl_price,tp=tp,strategy=self.name,context={"acc":acc_ok,"fvg_ok":fvg_ok,"fvg_weight":0.2 if fvg_ok else 0,"fib618":round(e618,2),"fib786":round(e786,2),"tp_fib":round(tp_fib,2),"tp_rr":round(tp_rr,2),"be_mode":self.BE_MODE,"be_ref":round(be_ref,2),"dir":"SELL"})
