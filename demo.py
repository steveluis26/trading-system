#!/usr/bin/env python3
"""Demo Unificado — v4 SMC vs v2 Wyckoff. Fusiona Wyckoff Lab de Hermes (todos los controles) + comparativa en paralelo con capital.
Base: github trading_system. Uso: streamlit run demo.py
"""
import streamlit as st
import pandas as pd, numpy as np, sys, collections
from datetime import datetime, timezone, timedelta
sys.path.insert(0, ".")
from data.loader import load_set
from core.types import Timeframe
from risk.config import RiskConfig
from backtest.multitf import MultiTFBacktester
from measurement.metrics import compute
from strategies.smc_multitf import SMCMultiTF
try:
    from strategies.wyckoff_v2 import WyckoffV2
    HAS_V2=True
except: HAS_V2=False
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Demo Unificado — SMC v4 vs Wyckoff v2", layout="wide", initial_sidebar_state="expanded")
st.title("🔬 Demo Unificado — SMC v4 vs Wyckoff v2")
st.caption("Base: github trading_system | Datos reales M5 2024-08-26→2026-05-15 | Costos netos | Compara en paralelo")

SYMS=["XAUUSD","EURUSD","GBPUSD"]
TF_MAP={"5m":Timeframe.M5,"15m":Timeframe.M15,"1h":Timeframe.H1}

# ── Sidebar: Controles Hermes completos + extras ──
with st.sidebar:
    st.header("Comparativa Backtest")
    strat_opt=st.selectbox("Estrategia", ["Ambas (comparar)", "v4 SMC (sesiones)", "v2 Wyckoff (Fib+FVG)"])
    sym=st.selectbox("Símbolo", SYMS, index=0)
    equity=st.number_input("Capital inicial $", value=10000, step=1000, help="Equity para cada estrategia en paralelo")
    st.markdown("---")
    st.header("Wyckoff Lab — Controls")
    tf=st.selectbox("Primary Timeframe", ["5m","15m","1h"], index=1)
    N_SWINGS=st.slider("Swing Lookback (N bars)", 3,10,5)
    ATR_MULT=st.slider("ATR Multiplier (accumulation range)", 0.5,3.0,1.5,0.1)
    MIN_GAP_ATR=st.slider("Min Gap ATR for FVG", 0.05,0.5,0.2,0.05)
    MIN_ACC_BARS=st.slider("Min Bars for Accumulation", 10,100,20)
    VOL_LOOKBACK=st.slider("Volume Lookback (bars)", 10,50,20)
    VOL_MULT_THRESHOLD=st.slider("Volume Spike Threshold (x avg)", 1.0,3.0,1.2,0.1)
    DIVERGENCE_MULT=st.slider("Divergence Threshold (vol/price)", 1.0,3.0,1.5,0.1)
    st.markdown("**Fibonacci Levels**")
    FIB_LEVELS={}
    for lvl in ["0.236","0.382","0.5","0.618","0.786","1.0","1.272","1.414","1.618"]:
        FIB_LEVELS[lvl]=st.checkbox(f"Fib {lvl}", value=lvl in ["0.618","0.786","1.272","1.618"])
    st.markdown("**Sessions (UTC)**")
    LONDON_OPEN=st.time_input("London Open", value=datetime.strptime("08:00","%H:%M").time())
    LONDON_CLOSE=st.time_input("London Close", value=datetime.strptime("09:00","%H:%M").time())
    NY_OPEN=st.time_input("NY Open", value=datetime.strptime("13:30","%H:%M").time())
    NY_CLOSE=st.time_input("NY Close", value=datetime.strptime("14:30","%H:%M").time())
    ASIA_OPEN=st.time_input("Asia Open", value=datetime.strptime("00:00","%H:%M").time())
    ASIA_CLOSE=st.time_input("Asia Close", value=datetime.strptime("01:00","%H:%M").time())
    MAX_BARS=st.slider("Bars to Display (latest N)", 100,2000,500)
    st.markdown("**News Guard (from partner)**")
    SL_WIDEN_MULT=st.slider("SL Widen Multiplier (ATR)", 1.0,3.0,1.5,0.1)
    NEWS_WINDOW_MIN=st.slider("News Window (minutes before/after)", 5,60,15)
    st.markdown("---")
    run=st.button("▶️ Correr backtest AHORA", type="primary", use_container_width=True)
    st.caption("~25s por símbolo. Ambas = ~50s secuencial. Params Wyckoff se aplican al backtest v2.")

# ── Helpers Wyckoff visual (copiado de demo_wyckoff.py) ──
def atr(df, period=14):
    tr1=df['high']-df['low']; tr2=(df['high']-df['close'].shift()).abs(); tr3=(df['low']-df['close'].shift()).abs()
    return pd.concat([tr1,tr2,tr3],axis=1).max(axis=1).rolling(period).mean()
def detect_swings(df,n=5):
    h,l=df['high'].values,df['low'].values
    sh=np.zeros(len(df),bool); sl=np.zeros(len(df),bool)
    for i in range(n,len(df)-n):
        if h[i]==h[i-n:i+n+1].max(): sh[i]=True
        if l[i]==l[i-n:i+n+1].min(): sl[i]=True
    return sh,sl
def detect_fvg(df,min_gap_atr=0.2):
    av=atr(df).ffill().bfill().values; bull=[]; bear=[]
    for i in range(2,len(df)):
        gu=df['low'].iloc[i]-df['high'].iloc[i-2]; gd=df['low'].iloc[i-2]-df['high'].iloc[i]
        if gu>min_gap_atr*av[i]: bull.append((i,df['high'].iloc[i-2],df['low'].iloc[i]))
        if gd>min_gap_atr*av[i]: bear.append((i,df['low'].iloc[i-2],df['high'].iloc[i]))
    return bull,bear
def detect_accumulation(df,atr_mult=1.5,min_bars=20):
    av=atr(df).ffill().bfill(); rngs=[]; i=0
    while i<len(df):
        j=i; rh=df['high'].iloc[i]; rl=df['low'].iloc[i]
        while j<len(df) and (j-i)<200:
            rh=max(rh,df['high'].iloc[j]); rl=min(rl,df['low'].iloc[j])
            if rh-rl>atr_mult*av.iloc[j]: break
            j+=1
        if j-i>=min_bars: rngs.append((i,j-1,rh,rl))
        i=max(i+1,j)
    return rngs

@st.cache_data(show_spinner="Cargando datos...")
def load_data_cached(symbol):
    bars_by_tf=load_set(symbol, base="data/raw")
    dfs={}
    for k,enum in TF_MAP.items():
        if enum in bars_by_tf:
            bars=bars_by_tf[enum]
            df=pd.DataFrame([{"time":b.time,"open":b.open,"high":b.high,"low":b.low,"close":b.close,"volume":b.volume} for b in bars])
            if not df.empty: df=df.sort_values("time").reset_index(drop=True); dfs[k]=df
    return dfs

def run_bt(strategy,symbol,equity, wyckoff_params=None):
    COMMON_START=datetime(2024,8,26,tzinfo=timezone.utc); COMMON_END=datetime(2026,5,15,23,59,tzinfo=timezone.utc)
    set_=load_set(symbol,"data/raw")
    needed=[Timeframe.D1,Timeframe.H4,Timeframe.H1,Timeframe.M15,Timeframe.M5]
    for tf in needed: set_[tf]=[b for b in set_[tf] if COMMON_START<=b.time<=COMMON_END]
    m5=set_[Timeframe.M5]; t0,t1=m5[0].time,m5[-1].time
    aligned={tf:[b for b in set_[tf] if t0<=b.time<=t1] for tf in needed}
    # parchear params wyckoff si viene
    if wyckoff_params and hasattr(strategy,'ACC_ATR_MULT'):
        for k,v in wyckoff_params.items(): setattr(strategy,k,v)
    bt=MultiTFBacktester(strategy, RiskConfig.from_yaml(), initial_equity=equity)
    res=bt.run(aligned, Timeframe.M5)
    m=compute(res.positions, equity, RiskConfig.from_yaml())
    m["rejections"]=dict(collections.Counter(x["reason"].split("(")[0].strip() for x in res.rejections))
    m["positions"]=res.positions
    return m

# ── Main: Chart Wyckoff Lab (visual instantáneo) ──
st.subheader(f"Wyckoff Lab — {sym} {tf} (visual, sin backtest)")
dfs=load_data_cached(sym)
if tf in dfs:
    df=dfs[tf].tail(MAX_BARS).copy().reset_index(drop=True)
    sh,sl=detect_swings(df,N_SWINGS); bull_fvg,bear_fvg=detect_fvg(df,MIN_GAP_ATR); acc=detect_accumulation(df,ATR_MULT,MIN_ACC_BARS)
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=0.02,row_heights=[0.75,0.25],subplot_titles=(f"{sym} {tf} — Wyckoff Lab","Volume"))
    fig.add_trace(go.Candlestick(x=df.index,open=df['open'],high=df['high'],low=df['low'],close=df['close'],name="Price",increasing_line_color="#26a69a",decreasing_line_color="#ef5350"),row=1,col=1)
    sh_idx=np.where(sh)[0]; sl_idx=np.where(sl)[0]
    fig.add_trace(go.Scatter(x=sh_idx,y=df['high'].iloc[sh_idx],mode="markers",marker=dict(symbol="triangle-down",size=8,color="#ef5350"),name="Swing High"),row=1,col=1)
    fig.add_trace(go.Scatter(x=sl_idx,y=df['low'].iloc[sl_idx],mode="markers",marker=dict(symbol="triangle-up",size=8,color="#26a69a"),name="Swing Low"),row=1,col=1)
    for idx,top,bot in bull_fvg: fig.add_shape(type="rect",x0=idx-2,x1=idx,y0=top,y1=bot,fillcolor="rgba(38,166,154,0.15)",line_width=0,layer="below",row=1,col=1)
    for idx,bot,top in bear_fvg: fig.add_shape(type="rect",x0=idx-2,x1=idx,y0=bot,y1=top,fillcolor="rgba(239,83,80,0.15)",line_width=0,layer="below",row=1,col=1)
    for s,e,hi,lo in acc: fig.add_shape(type="rect",x0=s,x1=e,y0=lo,y1=hi,fillcolor="rgba(255,193,7,0.1)",line=dict(color="#ffc107",width=1,dash="dot"),layer="below",row=1,col=1)
    # fib
    last_hi=np.where(sh)[0][-1] if sh.any() else len(df)-1; last_lo=np.where(sl)[0][-1] if sl.any() else 0
    # fib niveles
    if last_lo<last_hi:
        lo_p=df['low'].iloc[last_lo]; hi_p=df['high'].iloc[last_hi]; diff=hi_p-lo_p
        fl={"0.236":lo_p+0.236*diff,"0.382":lo_p+0.382*diff,"0.5":lo_p+0.5*diff,"0.618":lo_p+0.618*diff,"0.786":lo_p+0.786*diff,"1.0":hi_p,"1.272":hi_p+0.272*diff,"1.414":hi_p+0.414*diff,"1.618":hi_p+0.618*diff}
    else:
        lo_p=df['high'].iloc[last_hi]; hi_p=df['low'].iloc[last_lo]; diff=hi_p-lo_p
        fl={}
    for lvl,price in fl.items():
        if FIB_LEVELS.get(lvl): fig.add_hline(y=price,line_dash="dash",line_color="#26a69a" if lvl in ["0.618","0.786"] else "#9e9e9e",row=1,col=1,annotation_text=f"Fib {lvl}: {price:.2f}")
    fig.add_trace(go.Bar(x=df.index,y=df['volume'],name="Volume",marker_color="rgba(158,158,158,0.4)"),row=2,col=1)
    fig.update_layout(template="plotly_dark",height=600,showlegend=False,xaxis_rangeslider_visible=False,margin=dict(l=20,r=20,t=30,b=10))
    st.plotly_chart(fig,use_container_width=True)
    c1,c2,c3,c4=st.columns(4); c1.metric("Swings H/L", f"{int(sh.sum())}/{int(sl.sum())}"); c2.metric("FVG bull/bear", f"{len(bull_fvg)}/{len(bear_fvg)}"); c3.metric("Acumulaciones", len(acc)); c4.metric("Barras", len(df))
else:
    st.warning(f"Sin datos {tf} para {sym}")

# ── Backtest comparativo ──
if run:
    wy_params={"ACC_ATR_MULT":ATR_MULT,"ACC_MIN_BARS":MIN_ACC_BARS,"ATR_PERIOD":14,"MIN_WICK_PCT":0.5,"MAX_DEPTH_ATR":1.0}
    to_run=[]
    if strat_opt in ["v4 SMC (sesiones)","Ambas (comparar)"]: to_run.append(("v4 SMC",SMCMultiTF()))
    if strat_opt in ["v2 Wyckoff (Fib+FVG)","Ambas (comparar)"]:
        if HAS_V2: w=WyckoffV2(); to_run.append(("v2 Wyckoff",w))
        else: st.error("Wyckoff v2 no cargó")
    results={}
    prog=st.progress(0); status=st.empty()
    for i,(name,obj) in enumerate(to_run):
        status.info(f"Corriendo {name} en {sym}... ({i+1}/{len(to_run)})")
        prog.progress(int(i/len(to_run)*100))
        try: results[name]=run_bt(obj,sym,equity, wy_params if "Wyckoff" in name else None)
        except Exception as e: st.error(f"{name} error: {e}"); import traceback; st.code(traceback.format_exc())
        prog.progress(int((i+1)/len(to_run)*100))
    status.empty(); prog.empty()
    if len(results)==2:
        c1,c2=st.columns(2)
        for col,(name,m) in zip([c1,c2], results.items()):
            with col:
                st.subheader(name); ver=m.get("veredicto","—"); col2="red" if "SIN EDGE" in ver or "INSUFICIENTE" in ver else "green"
                st.markdown(f"**:{col2}[{ver}]**")
                st.metric("PnL neto", f"${m.get('pnl_neto',0):,.2f}", f"{m.get('retorno_pct',0)}%")
                st.metric("Trades", m.get("n_trades",0)); st.metric("Win rate", f"{m.get('win_rate_pct',0)}%")
                st.metric("PF", m.get("profit_factor",0)); st.metric("Sharpe", m.get("sharpe_anual",0))
                st.metric("DD max", f"{m.get('max_drawdown_pct',0)}%")
                st.json({k:v for k,v in m.items() if k in ["pnl_neto","retorno_pct","n_trades","win_rate_pct","profit_factor","expectancy","max_drawdown_pct","sharpe_anual","sortino_anual","rejections"]})
        cmp=pd.DataFrame({k:{n:results[n].get(k,"—") for n in results} for k in ["pnl_neto","retorno_pct","n_trades","win_rate_pct","profit_factor","sharpe_anual","max_drawdown_pct","expectancy"]}).T
        st.dataframe(cmp,use_container_width=True)
        fig2=go.Figure()
        for n,m in results.items():
            pts=[equity]; bal=equity
            for p in m["positions"]: bal+=p.pnl(); pts.append(bal)
            if len(pts)>1: fig2.add_trace(go.Scatter(y=pts,mode="lines",name=n))
        fig2.update_layout(template="plotly_dark",height=380,yaxis_title="Equity $",xaxis_title="Trade #")
        st.plotly_chart(fig2,use_container_width=True)
    elif len(results)==1:
        n,m=list(results.items())[0]; st.subheader(f"{n} — {sym}"); st.markdown(f"**{m.get('veredicto','')}**")
        a,b,c,d=st.columns(4); a.metric("PnL",f"${m.get('pnl_neto',0):,.2f}"); b.metric("Trades",m.get("n_trades",0)); c.metric("Win",f"{m.get('win_rate_pct',0)}%"); d.metric("PF",m.get("profit_factor","—"))
        st.json(m)
else:
    st.info("👆 Ajusta controles de Hermes arriba y pulsa **Correr backtest AHORA**. 'Ambas' compara v4 vs v2 en paralelo con mismo capital.")
