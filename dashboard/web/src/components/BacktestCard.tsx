"use client";

import { BacktestMetrics } from "@/lib/api";

function verdictColor(v?: string) {
  if (!v) return "text-slate-400";
  if (v.startsWith("EDGE")) return "text-emerald-400";
  if (v.startsWith("PROMETEDOR")) return "text-amber-400";
  return "text-rose-400";
}

export function BacktestCard({ symbol, m }: { symbol: string; m: BacktestMetrics | null }) {
  if (!m) {
    return (
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <h3 className="text-sm font-semibold text-slate-300">{symbol}</h3>
        <p className="mt-3 text-xs text-slate-500">cargando…</p>
      </div>
    );
  }
  if (m.error) {
    return (
      <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
        <h3 className="text-sm font-semibold text-slate-300">{symbol}</h3>
        <p className="mt-3 text-xs text-rose-400">{m.error}</p>
      </div>
    );
  }
  const pnl = m.pnl_neto ?? 0;
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Backtest · {symbol}</h3>
        <span className="text-sm font-mono tabular-nums" style={{ color: pnl >= 0 ? "#34d399" : "#fb7185" }}>
          {pnl >= 0 ? "+" : ""}${pnl.toFixed(0)}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="Trades" value={`${m.n_trades ?? 0}`} />
        <Stat label="Win %" value={`${(m.win_rate_pct ?? 0).toFixed(0)}`} />
        <Stat label="Sharpe" value={`${(m.sharpe_anual ?? 0).toFixed(2)}`} />
        <Stat label="PF" value={`${(m.profit_factor ?? 0).toFixed(2)}`} />
        <Stat label="DD %" value={`${(m.max_drawdown_pct ?? 0).toFixed(1)}`} />
        <Stat label="Días" value={`${m.periodo_dias ?? 0}`} />
      </div>
      <p className={`mt-3 text-xs font-medium ${verdictColor(m.veredicto)}`}>{m.veredicto}</p>
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
