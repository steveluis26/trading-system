/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars */
"use client";

import { useState, useEffect } from "react";
import {
  fetchWyckoffAnalysis,
  fetchCustomBacktest,
  fetchConfigDefaults,
  WyckoffAnalysisResponse,
  CustomBacktestParams,
  CustomBacktestResponse,
  ConfigDefaultsResponse,
} from "@/lib/api";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import { format } from "date-fns";

const SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"];

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function WyckoffDemo() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [analysis, setAnalysis] = useState<WyckoffAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [btResult, setBtResult] = useState<CustomBacktestResponse | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [defaults, setDefaults] = useState<ConfigDefaultsResponse | null>(null);
  const [params, setParams] = useState<CustomBacktestParams>({
    symbol: "XAUUSD",
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    initial_balance: 10000,
    risk_pct: 0.01,
    rr_ratio: 2.0,
    max_concurrent: 2,
    breakeven_enabled: true,
    partials_enabled: true,
    partial_at_pct: 40,
    partial_close_fraction: 0.33,
    kill_switch_daily: 5,
    kill_switch_monthly: 30,
    sl_pips: 45,
    wick_ratio_min: 0.5,
    max_penetration_atr: 1.0,
    volume_spike_mult: 1.5,
    news_guard_enabled: false,
  });
  const [lookbackDays, setLookbackDays] = useState(30);
  const [minSessions, setMinSessions] = useState(2);
  const [activeTab, setActiveTab] = useState<"analysis" | "backtest">("analysis");
  const [lab, setLab] = useState({
    timeframe: "15m" as "5m"|"15m"|"1h",
    swingLookback: 5,
    atrMult: 1.5,
    minGapAtr: 0.2,
    minBarsAcc: 20,
    volLookback: 20,
    volSpike: 1.2,
    divergenceMult: 1.5,
    fib: { "0.236": false, "0.382": false, "0.5": false, "0.618": true, "0.786": true, "1.0": false, "1.272": true, "1.414": true, "1.618": true } as Record<string, boolean>,
    londonOpen: "08:00", londonClose: "09:00",
    nyOpen: "13:30", nyClose: "14:30",
    asiaOpen: "00:00", asiaClose: "01:00",
    barsToDisplay: 500,
    slWidenMult: 1.5,
    newsWindowMin: 15,
  });

  // Load defaults on mount
  useEffect(() => {
    fetchConfigDefaults().then(setDefaults).catch(console.error);
  }, []);

  // Load analysis when symbol/params/lab change — lab sliders now trigger refetch with params
  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    const labParams = {
      swing_lookback: lab.swingLookback,
      atr_mult: lab.atrMult,
      min_gap_atr: lab.minGapAtr,
      min_bars_acc: lab.minBarsAcc,
      vol_lookback: lab.volLookback,
      vol_spike: lab.volSpike,
      divergence_mult: lab.divergenceMult,
      bars_to_display: lab.barsToDisplay,
      timeframe: lab.timeframe,
    };
    // pass lab as query string to wyckoff analysis
    const qs = new URLSearchParams({
      lookback_days: String(lookbackDays),
      min_sessions: String(minSessions),
      ...Object.fromEntries(Object.entries(labParams).map(([k,v]) => [k, String(v)])),
    });
    fetch(`${process.env.NEXT_PUBLIC_API || "http://127.0.0.1:8000"}/api/demo/wyckoff/${symbol}?${qs.toString()}`)
      .then(r=>r.json()).then(setAnalysis).catch(console.error).finally(()=>setLoading(false));
  }, [symbol, lookbackDays, minSessions, lab]);

  const handleRunBacktest = async () => {
    setBtLoading(true);
    try {
      const result = await fetchCustomBacktest(params);
      setBtResult(result);
      setActiveTab("backtest");
    } catch (e) {
      console.error(e);
    } finally {
      setBtLoading(false);
    }
  };

  const handleParamChange = (key: keyof CustomBacktestParams, value: any) => {
    setParams((p) => ({ ...p, [key]: value, symbol }));
  };

  // Prepare candlestick data for chart (simplified - using last 100 M5 candles)
  const chartData: CandleData[] = analysis?.timeframe_analysis
    ? Array.from({ length: 50 }, (_, i) => ({
        time: new Date(Date.now() - (49 - i) * 5 * 60 * 1000).toISOString(),
        open: 0,
        high: 0,
        low: 0,
        close: 0,
        volume: 0,
      }))
    : [];

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="flex items-center gap-4">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-lg bg-slate-800/50 px-3 py-2 text-sm ring-1 ring-white/5"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <div className="flex gap-2 text-xs text-slate-400">
            <label className="flex items-center gap-1">
              Lookback:
              <input
                type="number"
                value={lookbackDays}
                onChange={(e) => setLookbackDays(Number(e.target.value))}
                min={7}
                max={180}
                className="w-16 rounded bg-slate-800/50 px-2 py-1 text-xs ring-1 ring-white/5"
              />
            </label>
            <label className="flex items-center gap-1">
              Min Sessions:
              <input
                type="number"
                value={minSessions}
                onChange={(e) => setMinSessions(Number(e.target.value))}
                min={1}
                max={3}
                className="w-12 rounded bg-slate-800/50 px-2 py-1 text-xs ring-1 ring-white/5"
              />
            </label>
          </div>
        </div>
        {loading && <span className="text-xs text-sky-400 animate-pulse">Analizando…</span>}
      </div>

      {/* Wyckoff Lab — Controls (Hermes full set) */}
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <h3 className="text-sm font-semibold text-slate-200 mb-1">Wyckoff Lab — Controls</h3>
        <p className="text-[11px] text-slate-500 mb-4">Todos editables en vivo, sin tocar código. Cambia y pulsa Backtest Live.</p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1">
            <label className="text-xs text-slate-400">Primary Timeframe</label>
            <select value={lab.timeframe} onChange={(e)=>setLab({...lab, timeframe: e.target.value as any})} className="w-full rounded-lg bg-slate-800/50 px-3 py-2 text-sm ring-1 ring-white/5">
              <option value="5m">5m</option><option value="15m">15m</option><option value="1h">1h</option>
            </select>
          </div>
          <SliderInput label="Swing Lookback (N bars)" value={lab.swingLookback} min={3} max={10} step={1} onChange={(v)=>setLab({...lab, swingLookback:v})} />
          <SliderInput label="ATR Multiplier (acc range)" value={lab.atrMult} min={0.5} max={3} step={0.1} onChange={(v)=>setLab({...lab, atrMult:v})} />
          <SliderInput label="Min Gap ATR for FVG" value={lab.minGapAtr} min={0.05} max={0.5} step={0.05} onChange={(v)=>setLab({...lab, minGapAtr:v})} />
          <SliderInput label="Min Bars for Accumulation" value={lab.minBarsAcc} min={10} max={100} step={5} onChange={(v)=>setLab({...lab, minBarsAcc:v})} />
          <SliderInput label="Volume Lookback (bars)" value={lab.volLookback} min={10} max={50} step={5} onChange={(v)=>setLab({...lab, volLookback:v})} />
          <SliderInput label="Volume Spike Threshold (x avg)" value={lab.volSpike} min={1} max={3} step={0.1} onChange={(v)=>setLab({...lab, volSpike:v})} />
          <SliderInput label="Divergence Threshold (vol/price)" value={lab.divergenceMult} min={1} max={3} step={0.1} onChange={(v)=>setLab({...lab, divergenceMult:v})} />
          <SliderInput label="Bars to Display (latest N)" value={lab.barsToDisplay} min={100} max={2000} step={100} onChange={(v)=>setLab({...lab, barsToDisplay:v})} />
          <SliderInput label="SL Widen Multiplier (ATR)" value={lab.slWidenMult} min={1} max={3} step={0.1} onChange={(v)=>setLab({...lab, slWidenMult:v})} />
          <SliderInput label="News Window (minutes)" value={lab.newsWindowMin} min={5} max={60} step={5} onChange={(v)=>setLab({...lab, newsWindowMin:v})} />
        </div>
        <div className="mt-4">
          <div className="text-xs text-slate-400 mb-2">Fibonacci Levels</div>
          <div className="flex flex-wrap gap-2">
            {Object.keys(lab.fib).map(k=>(
              <label key={k} className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ring-1 cursor-pointer ${lab.fib[k] ? "bg-sky-500/20 text-sky-300 ring-sky-500/30" : "bg-slate-800/50 text-slate-400 ring-white/5"}`}>
                <input type="checkbox" checked={lab.fib[k]} onChange={(e)=>setLab({...lab, fib:{...lab.fib, [k]: e.target.checked}})} className="accent-sky-500" />
                Fib {k}
              </label>
            ))}
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg bg-slate-800/40 p-3 ring-1 ring-white/5">
            <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">Sessions (UTC)</div>
            <div className="space-y-2 text-xs">
              <div className="flex gap-2 items-center"><span className="w-24 text-slate-400">London</span><input type="time" value={lab.londonOpen} onChange={(e)=>setLab({...lab, londonOpen:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /><input type="time" value={lab.londonClose} onChange={(e)=>setLab({...lab, londonClose:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /></div>
              <div className="flex gap-2 items-center"><span className="w-24 text-slate-400">NY</span><input type="time" value={lab.nyOpen} onChange={(e)=>setLab({...lab, nyOpen:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /><input type="time" value={lab.nyClose} onChange={(e)=>setLab({...lab, nyClose:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /></div>
              <div className="flex gap-2 items-center"><span className="w-24 text-slate-400">Asia</span><input type="time" value={lab.asiaOpen} onChange={(e)=>setLab({...lab, asiaOpen:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /><input type="time" value={lab.asiaClose} onChange={(e)=>setLab({...lab, asiaClose:e.target.value})} className="flex-1 rounded bg-slate-900 px-2 py-1 ring-1 ring-white/5" /></div>
            </div>
          </div>
          <div className="md:col-span-2 flex items-center">
            <div className="text-[11px] leading-relaxed text-slate-500">Gráfica: XAUUSD {lab.timeframe} — últimos {lab.barsToDisplay} velas. Swings, FVG, acumulación, Fib y volumen se recalculan con estos sliders. Para demo con tu socia, mueve los valores y ejecuta Backtest Live sin tocar código.</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-slate-800/30 p-1 ring-1 ring-white/5">
        <button
          onClick={() => setActiveTab("analysis")}
          className={`px-4 py-2 text-sm font-medium rounded-md transition ${
            activeTab === "analysis"
              ? "bg-sky-500 text-white"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Análisis Wyckoff
        </button>
        <button
          onClick={() => setActiveTab("backtest")}
          className={`px-4 py-2 text-sm font-medium rounded-md transition ${
            activeTab === "backtest"
              ? "bg-emerald-500 text-white"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Backtest Live
        </button>
      </div>

      {activeTab === "analysis" && analysis && (
        <WyckoffAnalysisView data={analysis} />
      )}

      {activeTab === "backtest" && (
        <BacktestLiveView
          params={params}
          defaults={defaults}
          onParamChange={handleParamChange}
          onRun={handleRunBacktest}
          loading={btLoading}
          result={btResult}
        />
      )}
    </div>
  );
}

function WyckoffAnalysisView({ data }: { data: WyckoffAnalysisResponse }) {
  const { timeframe_analysis } = data;
  const { macro, wyckoff, setup_zone, confluence_zones, detected_sweeps, signals, volume_divergence, session_levels } = timeframe_analysis;

  const phaseColor = wyckoff.phase === "ACCUMULATION" ? "text-sky-400" :
    wyckoff.phase === "DISTRIBUTION" ? "text-orange-400" :
    wyckoff.phase === "MARKUP" ? "text-emerald-400" :
    wyckoff.phase === "MARKDOWN" ? "text-rose-400" : "text-slate-400";

  return (
    <div className="space-y-6">
      {/* Phase & Macro Header */}
      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard
          label="Fase Wyckoff"
          value={wyckoff.phase}
          sub={`${(wyckoff.confidence * 100).toFixed(0)}% confidence`}
          valueClass={phaseColor}
        />
        <MetricCard
          label="Tendencia Macro"
          value={macro.trend}
          sub={macro.trend === "BULLISH" ? "📈" : macro.trend === "BEARISH" ? "📉" : "↔️"}
          valueClass={macro.trend === "BULLISH" ? "text-emerald-400" : macro.trend === "BEARISH" ? "text-rose-400" : "text-slate-400"}
        />
        <MetricCard
          label="Setup Zone"
          value={setup_zone ? setup_zone.price.toFixed(2) : "—"}
          sub={setup_zone ? (setup_zone.is_low ? "Soporte" : "Resistencia") : "Ninguna"}
        />
        <MetricCard
          label="Divergencia Vol/Precio"
          value={volume_divergence.divergence_detected ? "SÍ" : "NO"}
          sub={volume_divergence.divergence_detected ? `${volume_divergence.events.length} eventos` : "Limpio"}
          valueClass={volume_divergence.divergence_detected ? "text-amber-400" : "text-emerald-400"}
        />
      </div>

      {/* Sessions Levels */}
      {session_levels && (
        <SessionLevelsCard levels={session_levels} />
      )}

      {/* Confluence Zones */}
      {confluence_zones.length > 0 && (
        <ConfluenceZonesCard zones={confluence_zones} />
      )}

      {/* Sweeps & Signals */}
      <div className="grid gap-4 md:grid-cols-2">
        {detected_sweeps.length > 0 && (
          <SweepsCard sweeps={detected_sweeps} />
        )}
        {signals.length > 0 && (
          <SignalsCard signals={signals} />
        )}
      </div>

      {/* Volume Divergence Details */}
      {volume_divergence.divergence_detected && volume_divergence.events.length > 0 && (
        <VolumeDivergenceCard events={volume_divergence.events} />
      )}
    </div>
  );
}

function SessionLevelsCard({ levels }: { levels: any }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Niveles de Sesión (México TZ)</h3>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <SessionLevelItem label="Asia H" value={levels.asia_high?.toFixed(2) || "—"} />
        <SessionLevelItem label="Asia L" value={levels.asia_low?.toFixed(2) || "—"} />
        <SessionLevelItem label="London H" value={levels.london_high?.toFixed(2) || "—"} />
        <SessionLevelItem label="London L" value={levels.london_low?.toFixed(2) || "—"} />
        <SessionLevelItem label="NY H" value={levels.ny_high?.toFixed(2) || "—"} />
        <SessionLevelItem label="NY L" value={levels.ny_low?.toFixed(2) || "—"} />
        <SessionLevelItem label="KZ H" value={levels.kill_zone_high?.toFixed(2) || "—"} />
        <SessionLevelItem label="KZ L" value={levels.kill_zone_low?.toFixed(2) || "—"} />
        <SessionLevelItem label="Spread KZ" value={levels.kill_zone_high && levels.kill_zone_low ? (levels.kill_zone_high - levels.kill_zone_low).toFixed(2) : "—"} />
      </div>
    </div>
  );
}

function SessionLevelItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-800/40 py-2 ring-1 ring-white/5">
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="text-sm font-mono tabular-nums text-slate-100">{value}</div>
    </div>
  );
}

function ConfluenceZonesCard({ zones }: { zones: any[] }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Zonas de Confluencia ({zones.length})</h3>
      <div className="max-h-48 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-2 py-1">Precio</th>
              <th className="px-2 py-1">Tipo</th>
              <th className="px-2 py-1">Sesiones</th>
              <th className="px-2 py-1">Fuerza</th>
            </tr>
          </thead>
          <tbody>
            {zones.map((z, i) => (
              <tr key={i} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-2 py-1 font-mono tabular-nums">{z.price.toFixed(2)}</td>
                <td className="px-2 py-1">
                  <span className={`rounded px-1.5 py-0.5 text-[9px] ${z.is_high ? "bg-rose-500/20 text-rose-400" : "bg-emerald-500/20 text-emerald-400"}`}>
                    {z.is_high ? "HIGH" : z.is_low ? "LOW" : "MIX"}
                  </span>
                </td>
                <td className="px-2 py-1 text-slate-400">{z.sessions.join(", ")}</td>
                <td className="px-2 py-1 font-semibold text-sky-400">{z.strength} sesiones</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SweepsCard({ sweeps }: { sweeps: any[] }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Barridos Detectados ({sweeps.length})</h3>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="px-2 py-1">Nivel</th><th className="px-2 py-1">Dir</th><th className="px-2 py-1">Penetración</th><th className="px-2 py-1">Wick</th><th className="px-2 py-1">Reclaim</th><th className="px-2 py-1">Vol Spike</th></tr>
          </thead>
          <tbody>
            {sweeps.slice(0, 10).map((s, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className="px-2 py-1 font-mono tabular-nums">{s.level.toFixed(2)}</td>
                <td className={`px-2 py-1 ${s.direction === "LONG" ? "text-emerald-400" : "text-rose-400"}`}>{s.direction}</td>
                <td className="px-2 py-1 font-mono">{s.penetration_pips.toFixed(1)} pips</td>
                <td className="px-2 py-1">{(s.wick_ratio * 100).toFixed(0)}%</td>
                <td className="px-2 py-1">{s.candles_to_reclaim}</td>
                <td className="px-2 py-1">{(s.volume_spike * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SignalsCard({ signals }: { signals: any[] }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Señales de Entrada ({signals.length})</h3>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="px-2 py-1">Dir</th><th className="px-2 py-1">Entry</th><th className="px-2 py-1">SL</th><th className="px-2 py-1">TP</th><th className="px-2 py-1">RR</th><th className="px-2 py-1">Conf</th></tr>
          </thead>
          <tbody>
            {signals.slice(0, 10).map((s, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className={`px-2 py-1 ${s.direction === "LONG" ? "text-emerald-400" : "text-rose-400"}`}>{s.direction}</td>
                <td className="px-2 py-1 font-mono tabular-nums">{s.entry_price.toFixed(2)}</td>
                <td className="px-2 py-1 font-mono tabular-nums">{s.sl_price.toFixed(2)}</td>
                <td className="px-2 py-1 font-mono tabular-nums">{s.tp_price.toFixed(2)}</td>
                <td className="px-2 py-1 font-mono">1:{s.tp_pips / s.sl_pips > 0 ? (s.tp_pips / s.sl_pips).toFixed(1) : "—"}</td>
                <td className="px-2 py-1">{(s.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VolumeDivergenceCard({ events }: { events: any[] }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5 border border-amber-500/30">
      <h3 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
        Divergencia Volumen-Precio Detectada ({events.length})
      </h3>
      <div className="max-h-48 overflow-y-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
            <tr><th className="px-2 py-1">Zona</th><th className="px-2 py-1">Tipo</th><th className="px-2 py-1">Vol Ratio</th><th className="px-2 py-1">Price Δ</th><th className="px-2 py-1">Interpretación</th></tr>
          </thead>
          <tbody>
            {events.slice(0, 10).map((e, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className="px-2 py-1 font-mono tabular-nums">{e.zone_price.toFixed(2)}</td>
                <td className="px-2 py-1">
                  <span className={`rounded px-1.5 py-0.5 text-[9px] ${e.type === "absorption" ? "bg-sky-500/20 text-sky-400" : "bg-orange-500/20 text-orange-400"}`}>
                    {e.type}
                  </span>
                </td>
                <td className="px-2 py-1 font-mono">{e.volume_ratio.toFixed(2)}x</td>
                <td className="px-2 py-1 font-mono">{e.price_change_pips.toFixed(1)} pips</td>
                <td className="px-2 py-1 text-slate-300">{e.interpretation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BacktestLiveView({
  params,
  defaults,
  onParamChange,
  onRun,
  loading,
  result,
}: {
  params: CustomBacktestParams;
  defaults: ConfigDefaultsResponse | null;
  onParamChange: (key: keyof CustomBacktestParams, value: any) => void;
  onRun: () => void;
  loading: boolean;
  result: CustomBacktestResponse | null;
}) {
  const riskDefaults = defaults?.risk;
  const instDefaults = defaults?.instruments?.[params.symbol];

  return (
    <div className="space-y-6">
      {/* Parameter Grid */}
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Parámetros de Backtest (Live)</h3>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <SliderInput
            label="Risk % / Trade"
            value={params.risk_pct * 100}
            min={0.1}
            max={10}
            step={0.1}
            suffix="%"
            onChange={(v) => onParamChange("risk_pct", v / 100)}
            defaultValue={riskDefaults?.risk_pct_per_trade ? riskDefaults.risk_pct_per_trade * 100 : 1}
          />
          <SliderInput
            label="Risk:Reward"
            value={params.rr_ratio}
            min={1}
            max={10}
            step={0.1}
            onChange={(v) => onParamChange("rr_ratio", v)}
            defaultValue={riskDefaults?.rr_ratio || 2}
          />
          <SliderInput
            label="SL Pips"
            value={params.sl_pips}
            min={10}
            max={200}
            step={1}
            suffix=" pips"
            onChange={(v) => onParamChange("sl_pips", v)}
            defaultValue={instDefaults?.spread_pips ? Math.max(20, instDefaults.spread_pips * 3) : 45}
          />
          <SliderInput
            label="Max Concurrent"
            value={params.max_concurrent}
            min={1}
            max={10}
            step={1}
            onChange={(v) => onParamChange("max_concurrent", v)}
            defaultValue={riskDefaults?.max_concurrent || 2}
          />
          <SliderInput
            label="Breakeven @ % TP"
            value={params.partial_at_pct}
            min={10}
            max={90}
            step={5}
            suffix="%"
            onChange={(v) => onParamChange("partial_at_pct", v)}
            defaultValue={riskDefaults?.breakeven_trigger_pct || 40}
          />
          <SliderInput
            label="Partial Close %"
            value={params.partial_close_fraction * 100}
            min={10}
            max={90}
            step={5}
            suffix="%"
            onChange={(v) => onParamChange("partial_close_fraction", v / 100)}
            defaultValue={riskDefaults?.partial_stages?.[0]?.close_fraction ? riskDefaults.partial_stages[0].close_fraction * 100 : 33}
          />
          <SliderInput
            label="Daily Kill Switch"
            value={params.kill_switch_daily}
            min={1}
            max={20}
            step={0.5}
            suffix="%"
            onChange={(v) => onParamChange("kill_switch_daily", v)}
            defaultValue={riskDefaults?.max_daily_loss || 5}
          />
          <SliderInput
            label="Monthly Kill Switch"
            value={params.kill_switch_monthly}
            min={5}
            max={50}
            step={1}
            suffix="%"
            onChange={(v) => onParamChange("kill_switch_monthly", v)}
            defaultValue={riskDefaults?.max_monthly_loss || 30}
          />
          <SliderInput
            label="Wick Ratio Min"
            value={params.wick_ratio_min}
            min={0.1}
            max={1}
            step={0.05}
            onChange={(v) => onParamChange("wick_ratio_min", v)}
            defaultValue={riskDefaults?.wick_ratio_min || 0.5}
          />
          <SliderInput
            label="Max Penetration ATR"
            value={params.max_penetration_atr}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(v) => onParamChange("max_penetration_atr", v)}
            defaultValue={riskDefaults?.max_penetration_atr || 1}
          />
          <SliderInput
            label="Volume Spike Mult"
            value={params.volume_spike_mult}
            min={0.5}
            max={5}
            step={0.1}
            onChange={(v) => onParamChange("volume_spike_mult", v)}
            defaultValue={riskDefaults?.volume_spike_mult || 1.5}
          />
          <div className="flex items-center gap-2 md:col-span-2">
            <input
              type="checkbox"
              id="breakeven_enabled"
              checked={params.breakeven_enabled}
              onChange={(e) => onParamChange("breakeven_enabled", e.target.checked)}
              className="w-4 h-4 accent-sky-500"
            />
            <label htmlFor="breakeven_enabled" className="text-sm text-slate-300">Breakeven Enabled</label>
            <input
              type="checkbox"
              id="partials_enabled"
              checked={params.partials_enabled}
              onChange={(e) => onParamChange("partials_enabled", e.target.checked)}
              className="w-4 h-4 accent-sky-500 ml-6"
            />
            <label htmlFor="partials_enabled" className="text-sm text-slate-300">Partials Enabled</label>
            <input
              type="checkbox"
              id="news_guard_enabled"
              checked={params.news_guard_enabled}
              onChange={(e) => onParamChange("news_guard_enabled", e.target.checked)}
              className="w-4 h-4 accent-sky-500 ml-6"
            />
            <label htmlFor="news_guard_enabled" className="text-sm text-slate-300">News Guard</label>
          </div>
        </div>

        {/* Date Range & Balance */}
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <DateInput
            label="Start Date"
            value={params.start_date}
            onChange={(v) => onParamChange("start_date", v)}
          />
          <DateInput
            label="End Date"
            value={params.end_date}
            onChange={(v) => onParamChange("end_date", v)}
          />
          <NumberInput
            label="Initial Balance"
            value={params.initial_balance}
            onChange={(v) => onParamChange("initial_balance", v)}
            step={1000}
          />
        </div>
      </div>

      {/* Run Button */}
      <button
        onClick={onRun}
        disabled={loading}
        className="w-full sm:w-auto px-6 py-3 rounded-xl bg-sky-500/20 border border-sky-500/30 text-sky-400 font-semibold hover:bg-sky-500/30 transition disabled:opacity-50"
      >
        {loading ? "Ejecutando Backtest…" : "▶ Ejecutar Backtest Personalizado"}
      </button>

      {/* Results */}
      {result && (
        <BacktestResultsCard result={result} />
      )}
    </div>
  );
}

function SliderInput({
  label,
  value,
  min,
  max,
  step,
  suffix = "",
  onChange,
  defaultValue,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (v: number) => void;
  defaultValue?: number;
}) {
  return (
    <div className="space-y-1">
      <label className="flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-mono tabular-nums text-sky-400">{value}{suffix}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-sky-500"
      />
      {defaultValue !== undefined && (
        <div className="text-[9px] text-slate-500">Default: {defaultValue}{suffix}</div>
      )}
    </div>
  );
}

function DateInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-slate-400">{label}</label>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg bg-slate-800/50 px-3 py-2 text-sm ring-1 ring-white/5"
      />
    </div>
  );
}

function NumberInput({ label, value, onChange, step = 1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-slate-400">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        step={step}
        className="w-full rounded-lg bg-slate-800/50 px-3 py-2 text-sm ring-1 ring-white/5"
      />
    </div>
  );
}

function BacktestResultsCard({ result }: { result: CustomBacktestResponse }) {
  if (result.error) {
    return (
      <div className="rounded-2xl bg-rose-500/10 p-5 ring-1 ring-rose-500/30">
        <p className="text-rose-400">Error: {result.error}</p>
      </div>
    );
  }

  const pnl = result.pnl_neto;
  const equityData = result.daily.map(([date, equity]) => ({
    date: format(new Date(date), "MMM dd"),
    equity,
  }));

  return (
    <div className="space-y-4">
      {/* Summary Metrics */}
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-300">Resultados Backtest</h3>
          <span className={`text-lg font-mono tabular-nums ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {pnl >= 0 ? "+" : ""}${pnl.toFixed(0)} ({result.retorno_pct > 0 ? "+" : ""}{result.retorno_pct.toFixed(1)}%)
          </span>
        </div>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-center">
          <Stat label="Trades" value={`${result.n_trades}`} />
          <Stat label="Win %" value={`${result.win_rate_pct.toFixed(1)}`} />
          <Stat label="PF" value={`${result.profit_factor.toFixed(2)}`} />
          <Stat label="Sharpe" value={`${result.sharpe_anual.toFixed(2)}`} />
          <Stat label="Max DD %" value={`${result.max_drawdown_pct.toFixed(1)}`} />
        </div>
      </div>

      {/* Equity Curve */}
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Equity Curve</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equityData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} axisLine={false} tickLine={false} tickFormatter={(v) => "$" + v.toLocaleString()} />
              <Tooltip
                contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
              />
              <Area type="monotone" dataKey="equity" stroke="#34d399" strokeWidth={2} fillOpacity={1} fill="url(#colorEquity)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Trades Table */}
      {result.trades.length > 0 && (
        <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Trades Ejecutados ({result.trades.length})</h3>
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-2 py-1">Entry</th>
                  <th className="px-2 py-1">Exit</th>
                  <th className="px-2 py-1">Dir</th>
                  <th className="px-2 py-1">Entry Px</th>
                  <th className="px-2 py-1">Exit Px</th>
                  <th className="px-2 py-1">PnL $</th>
                  <th className="px-2 py-1">PnL %</th>
                  <th className="px-2 py-1">Reason</th>
                  <th className="px-2 py-1">Dur</th>
                  <th className="px-2 py-1">SL/TP</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.slice(0, 30).map((t, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="px-2 py-1 font-mono text-slate-400">{format(new Date(t.entry_time), "MM/dd HH:mm")}</td>
                    <td className="px-2 py-1 font-mono text-slate-400">{t.exit_time ? format(new Date(t.exit_time), "MM/dd HH:mm") : "—"}</td>
                    <td className={`px-2 py-1 ${t.direction === "LONG" ? "text-emerald-400" : "text-rose-400"}`}>{t.direction}</td>
                    <td className="px-2 py-1 font-mono tabular-nums">{t.entry_price.toFixed(2)}</td>
                    <td className="px-2 py-1 font-mono tabular-nums">{t.exit_price?.toFixed(2) || "—"}</td>
                    <td className={`px-2 py-1 font-mono ${t.pnl_usd >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{t.pnl_usd >= 0 ? "+" : ""}${t.pnl_usd.toFixed(0)}</td>
                    <td className={`px-2 py-1 ${t.pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(1)}%</td>
                    <td className="px-2 py-1 text-slate-400">{t.exit_reason}</td>
                    <td className="px-2 py-1 text-slate-400">{t.duration_min}m</td>
                    <td className="px-2 py-1 font-mono text-xs">SL {t.sl_pips.toFixed(0)} / TP {t.tp_pips.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rejections */}
      {result.rejections && Object.keys(result.rejections).length > 0 && (
        <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Rechazos Risk Engine</h3>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(result.rejections).map(([k, v]) => (
              <span key={k} className="rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] text-slate-300">{k}: {v}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, sub, valueClass = "text-white" }: { label: string; value: string; sub: string; valueClass?: string }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`mt-1 text-xl font-bold ${valueClass}`}>{value}</div>
      <div className="mt-1 text-xs text-slate-400">{sub}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-800/40 py-2 ring-1 ring-white/5">
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="text-sm font-semibold tabular-nums text-slate-100">{value}</div>
    </div>
  );
}

export default WyckoffDemo;