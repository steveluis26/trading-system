"use client";

import { PanelSnapshot } from "@/lib/api";

function biasColor(b: string) {
  if (b === "ALCISTA") return "text-emerald-400";
  if (b === "BAJISTA") return "text-rose-400";
  return "text-amber-400";
}

function flowColor(l: string) {
  if (l === "COMPRA") return "text-emerald-400";
  if (l === "VENTA") return "text-rose-400";
  return "text-slate-300";
}

function Metric({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-slate-800/40 px-3 py-2 ring-1 ring-white/5">
      <span className="text-[10px] uppercase tracking-widest text-slate-500">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${accent ?? "text-slate-100"}`}>{value}</span>
      {sub && <span className="text-[10px] text-slate-500">{sub}</span>}
    </div>
  );
}

export function PairCard({ symbol, p }: { symbol: string; p: PanelSnapshot | null }) {
  if (!p || p.error) {
    return (
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold tracking-tight text-slate-100">{symbol}</h3>
          <span className="text-xs text-slate-500">sin datos M5</span>
        </div>
        <p className="mt-4 text-sm text-slate-500">El histórico de 5m de 2 años aún no está disponible.</p>
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5 backdrop-blur transition hover:ring-emerald-500/30">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h3 className="text-lg font-bold tracking-tight text-slate-100">{symbol}</h3>
          <span className="text-xs text-slate-500">{p.time}</span>
        </div>
        <span className="font-mono text-base font-semibold text-slate-100 tabular-nums">{p.price.toFixed(5)}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Metric label="Tendencia Macro" value={p.tendencia_macro} accent={biasColor(p.tendencia_macro)} sub={p.tendencia_detail} />
        <Metric label="Flujo Inmediato (VSA)" value={`${p.flujo_pct_comprador}%`} accent={flowColor(p.flujo_label)} sub={p.flujo_label} />
        <Metric label="Volumen (5v)" value={p.volumen_5v.toLocaleString()} sub={`rel ${p.volumen_rel.toFixed(2)}x`} />
        <Metric label="Volatilidad ATR" value={p.atr.toFixed(5)} accent={p.atr_regime === "ALTA" ? "text-amber-400" : "text-slate-100"} sub={p.atr_regime} />
      </div>

      <div className="mt-3 rounded-lg bg-slate-800/40 px-3 py-2 ring-1 ring-white/5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="uppercase tracking-widest text-slate-500">Liquidez en Radar</span>
          <span className="text-slate-400">
            <span className="text-emerald-400">▲ {p.liquidez_arriba}</span>{" "}
            <span className="text-rose-400">▼ {p.liquidez_abajo}</span>
          </span>
        </div>
        <p className="mt-1 text-[10px] text-slate-500">{p.liquidez_detalle}</p>
      </div>
    </div>
  );
}
