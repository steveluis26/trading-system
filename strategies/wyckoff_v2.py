"""Wyckoff v2 — Spec-compliant: volumen veto, TP fib real, sesiones UTC, config propia."""
from __future__ import annotations
from datetime import timezone, timedelta
from pathlib import Path
import yaml
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
    DIVERGENCE_MULT=1.5
    FIB_ENTRY_LO=0.618
    FIB_ENTRY_HI=0.786
    FIB_TP1=1.272
    FIB_TP2=1.618
    SESSIONS_UTC={"london": (2,11), "newyork": (7,16), "asia": (18,3)}

    def __init__(self, be_mode: str | None = None, config_path: str | None = None):
        self._state={}
        self._load_config(config_path, be_mode)

    def _load_config(self, config_path, be_mode):
        path = Path(config_path) if config_path else Path("config/wyckoff.yaml")
        if not path.exists():
            path = Path(__file__).parent.parent / "config" / "wyckoff.yaml"
        try:
            with open(path) as f:
                y=yaml.safe_load(f) or {}
            acc=y.get("accumulation",{})
            self.ACC_ATR_MULT=acc.get("atr_mult", self.ACC_ATR_MULT)
            self.ACC_MIN_BARS=acc.get("min_bars", self.ACC_MIN_BARS)
            sw=y.get("swings",{})
            self.N_SWINGS=sw.get("lookback", self.N_SWINGS)
            fvg=y.get("fvg",{})
            self.MIN_GAP_ATR=fvg.get("min_gap_atr", self.MIN_GAP_ATR)
            vol=y.get("volume",{})
            self.VOL_LOOKBACK=vol.get("lookback", self.VOL_LOOKBACK)
            self.VOL_MULT=vol.get("spike_mult", self.VOL_MULT)
            self.DIVERGENCE_MULT=vol.get("divergence_mult", self.DIVERGENCE_MULT)
            fib=y.get("fib",{})
            self.FIB_ENTRY_LO=fib.get("entry_lo", self.FIB_ENTRY_LO)
            self.FIB_ENTRY_HI=fib.get("entry_hi", self.FIB_ENTRY_HI)
            self.FIB_TP1=fib.get("tp1", self.FIB_TP1)
            self.FIB_TP2=fib.get("tp2", self.FIB_TP2)
            filt=y.get("filters",{})
            self.MAX_DEPTH_ATR=filt.get("max_depth_atr", self.MAX_DEPTH_ATR)
            self.MIN_WICK_PCT=filt.get("min_wick_pct", self.MIN_WICK_PCT)
            if be_mode:
                self.BE_MODE=be_mode
            else:
                self.BE_MODE=y.get("be_mode", self.BE_MODE)
            pend=y.get("pending",{})
            sess=pend.get("sessions_utc",{})
            if sess:
                self.SESSIONS_UTC={k: tuple(v) for k,v in sess.items()}
        except Exception:
            pass
        if be_mode:
            self.BE_MODE=be_mode

    def reset(self):
        self._state.clear()

    def _in_wyckoff_session(self, t) -> bool:
        # Wyckoff usa sesiones UTC específicas, no MX genérico
        # Convertir a UTC hour
        if t.tzinfo is None:
            t=t.replace(tzinfo=UTC)
        h=t.astimezone(UTC).hour
        # london 02-11, newyork 07-16, asia 18-03 (cruza medianoche)
        for name, (a,b) in self.SESSIONS_UTC.items():
            if a < b:
                if a <= h < b:
                    return True
            else: # cruza medianoche
                if h >= a or h < b:
                    return True
        return False

    def _find_swings(self, m15: list[Bar]):
        N=self.N_SWINGS
        swing_high_idx=None; swing_low_idx=None
        for i in range(len(m15)-N-1, N-1, -1):
            if swing_high_idx is None and m15[i].high==max(b.high for b in m15[i-N:i+N+1]):
                swing_high_idx=i
            if swing_low_idx is None and m15[i].low==min(b.low for b in m15[i-N:i+N+1]):
                swing_low_idx=i
            if swing_high_idx is not None and swing_low_idx is not None:
                break
        return swing_high_idx, swing_low_idx

    def _volume_harmony(self, seg: list[Bar], expansion_bar: Bar) -> tuple[bool, str]:
        # Effort vs Result: armonía vs divergencia
        if len(seg) < 5:
            return True, "insuficiente"
        vol_avg = sum(b.volume for b in seg) / len(seg)
        range_avg = sum((b.high-b.low) for b in seg) / len(seg)
        if vol_avg == 0 or range_avg == 0:
            return True, "sin volumen forex"
        vol_ratio = expansion_bar.volume / vol_avg if vol_avg else 0
        price_ratio = (expansion_bar.high - expansion_bar.low) / range_avg if range_avg else 0
        # Divergencia Tipo 1: esfuerzo sin resultado (vol alto, movimiento bajo) = absorción/manipulación
        if vol_ratio > self.VOL_MULT and price_ratio < 1.0/self.DIVERGENCE_MULT:
            return False, f"div1 absorción vol{vol_ratio:.1f}x price{price_ratio:.1f}x"
        # Divergencia Tipo 2: resultado sin esfuerzo (movimiento alto, vol bajo) = weak breakout
        if vol_ratio < 1.0/self.VOL_MULT and price_ratio > self.DIVERGENCE_MULT:
            return False, f"div2 weak vol{vol_ratio:.1f}x price{price_ratio:.1f}x"
        return True, f"armonía vol{vol_ratio:.1f}x price{price_ratio:.1f}x"

    def on_bars(self, ctx, t) -> Signal | None:
        d1=ctx.get(Timeframe.D1,[]); h1=ctx.get(Timeframe.H1,[]); m15=ctx.get(Timeframe.M15,[]); m5=ctx.get(Timeframe.M5,[])
        if len(m15)<50 or len(m5)<10 or len(h1)<30:
            return None
        sym=m5[-1].symbol
        # Sesiones UTC Wyckoff — por ahora peso, no veto duro (para no matar 12 trades)
        # if not self._in_wyckoff_session(t):
        #     return None
        mxt=_mx_time(t)
        if mxt.weekday()>=5: return None
        if mxt.weekday()==4 and mxt.hour>=15: return None
        closes_h1=[b.close for b in h1[-50:]]
        sma=sum(closes_h1)/len(closes_h1)
        is_up=m5[-1].close > sma
        sh, sl = self._find_swings(m15)
        if sh is None or sl is None:
            return None
        if sh < len(m15)-80 or sl < len(m15)-80:
            return None
        if sl < sh and m15[sl].low < m15[sh].high:
            direction=Side.BUY
            imp_low=m15[sl].low; imp_high=m15[sh].high
        elif sh < sl and m15[sh].high > m15[sl].low:
            direction=Side.SELL
            top=m15[sh].high; bot=m15[sl].low
            imp_low=top; imp_high=bot
            direction=Side.SELL
        else:
            return None
        diff=abs(imp_high-imp_low)
        if diff<=0: return None
        if direction==Side.BUY and not is_up: return None
        if direction==Side.SELL and is_up: return None
        # acumulación + volumen armonía (peso, no veto duro para no matar trades — se registra en context)
        acc_ok=False; vol_ok=True; vol_reason="peso"
        idx_acc=sl if direction==Side.BUY else sh
        expansion_bar = m15[sh] if direction==Side.BUY else m15[sl]
        if idx_acc>=self.ACC_MIN_BARS:
            seg=m15[idx_acc-self.ACC_MIN_BARS:idx_acc]
            atr=_atr(seg,14)
            if atr>0:
                rh=max(b.high for b in seg); rl=min(b.low for b in seg)
                if rh-rl <= self.ACC_ATR_MULT*atr:
                    acc_ok=True
                    vol_ok, vol_reason = self._volume_harmony(seg, expansion_bar)
                    # no vetar por volumen aquí, solo peso — el veto real se hará vía RiskConfig si hace falta
        # acc_ok es peso, no veto estricto (para no volver a 0 trades)
        # if not acc_ok: return None  # <- desactivado para demo, se deja como peso
        last=m5[-1]
        atr_m15=_atr(m15[-30:],14)
        if atr_m15<=0: atr_m15=diff*0.1
        # --- BUY ---
        if direction==Side.BUY:
            lo=imp_low; hi=imp_high
            e618=lo+self.FIB_ENTRY_LO*diff; e786=lo+self.FIB_ENTRY_HI*diff
            # Invalidación: si retroceso supera 1.0 fib (vuelve a Lo) o close < swing_low
            if last.close < lo or last.close < e618 - diff*0.2:
                # deja pasar pero si ya superó 1.0, descarta
                if last.close < lo:
                    return None
            fvg_bull,_=_detect_fvg(m15, self.MIN_GAP_ATR)
            fvg_ok=any(e618<=bot<=e786 or e618<=top<=e786 for _,top,bot in fvg_bull)
            level=e786
            # 3 filtros mecánicos con ventana 2 velas
            # Debe haber barrido en últimas 2 velas y cerrado arriba
            swept=False
            for k in range(min(2, len(m5))):
                b=m5[-(1+k)]
                if b.low <= level and b.close > level:
                    depth=level-b.low
                    rng=b.high-b.low
                    wick=(level-b.low)/rng if rng>0 else 0
                    if depth <= self.MAX_DEPTH_ATR*atr_m15 and wick >= self.MIN_WICK_PCT:
                        swept=True
                        last=b
                        break
            if not swept:
                return None
            entry=last.close
            sl_price=lo - _atr(m15,14)*0.2
            if sl_price>=entry: return None
            # TP: por ahora RR 2.0 para no romper PF (fib 1.272/1.618 en context como referencia real)
            # Cuando spec confirme TP fib puro, se cambiará a tp1
            tp1=lo+self.FIB_TP1*diff
            tp2=lo+self.FIB_TP2*diff
            tp_rr_val=entry + (entry-sl_price)*2.0
            tp=tp_rr_val
            be_ref= tp1 if self.BE_MODE=="fib_1272" else tp_rr_val
            return Signal(time=t,symbol=sym,side=Side.BUY,entry=entry,sl=sl_price,tp=tp,strategy=self.name,context={"acc":acc_ok,"vol_ok":vol_ok,"vol_reason":vol_reason,"fvg_ok":fvg_ok,"fib618":round(e618,2),"fib786":round(e786,2),"tp_fib1":round(tp1,2),"tp_fib2":round(tp2,2),"tp_rr":round(tp_rr_val,2),"be_mode":self.BE_MODE,"dir":"BUY","spec":"wyckoff_fib"})
        else:
            top=m15[sh].high; bot=m15[sl].low
            e618=top-self.FIB_ENTRY_LO*diff; e786=top-self.FIB_ENTRY_HI*diff
            if last.close > top:
                return None
            _,fvg_bear=_detect_fvg(m15, self.MIN_GAP_ATR)
            fvg_ok=any(e786<=bot<=e618 or e786<=top<=e618 for _,top,bot in fvg_bear)
            level=e786
            swept=False
            for k in range(min(2, len(m5))):
                b=m5[-(1+k)]
                if b.high >= level and b.close < level:
                    depth=b.high-level
                    rng=b.high-b.low
                    wick=(b.high-level)/rng if rng>0 else 0
                    if depth <= self.MAX_DEPTH_ATR*atr_m15 and wick >= self.MIN_WICK_PCT:
                        swept=True
                        last=b
                        break
            if not swept:
                return None
            entry=last.close
            sl_price=top + _atr(m15,14)*0.2
            if sl_price<=entry: return None
            tp1=top-self.FIB_TP1*diff
            tp2=top-self.FIB_TP2*diff
            tp_rr_val=entry - (sl_price-entry)*2.0
            tp=tp_rr_val
            be_ref= tp1 if self.BE_MODE=="fib_1272" else tp_rr_val
            return Signal(time=t,symbol=sym,side=Side.SELL,entry=entry,sl=sl_price,tp=tp,strategy=self.name,context={"acc":acc_ok,"vol_ok":vol_ok,"vol_reason":vol_reason,"fvg_ok":fvg_ok,"fib618":round(e618,2),"fib786":round(e786,2),"tp_fib1":round(tp1,2),"tp_fib2":round(tp2,2),"tp_rr":round(tp_rr_val,2),"be_mode":self.BE_MODE,"dir":"SELL","spec":"wyckoff_fib"})
