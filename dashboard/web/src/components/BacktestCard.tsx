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
        <h3 className="text-sm font-semibold text-slate-300">Backtest · {symbol} {m.strategy ? `· ${m.strategy}` : ""}</h3>
        <span className="text-sm font-mono tabular-nums" style={{ color: pnl >= 0 ? "#34d399" : "#fb7185" }}>
          {pnl >= 0 ? "+" : ""}${pnl.toFixed(0)} {m.retorno_pct !== undefined ? `(${m.retorno_pct > 0 ? "+" : ""}${m.retorno_pct.toFixed(1)}%)` : ""}
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
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat label="Expectancy" value={`${(m.expectancy ?? 0).toFixed(2)}`} />
        <Stat label="Payoff" value={`${(m.payoff_ratio ?? 0).toFixed(2)}`} />
        <Stat label="Retorno" value={`${(m.retorno_pct ?? 0).toFixed(1)}%`} />
      </div>
      {(m.rejections && Object.keys(m.rejections).length > 0) && (
        <div className="mt-3 rounded-lg bg-slate-800/30 p-2 ring-1 ring-white/5">
          <div className="text-[9px] uppercase tracking-widest text-slate-500">Rechazos Risk</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {Object.entries(m.rejections).map(([k,v]) => (
              <span key={k} className="rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] text-slate-300">{k}: {v}</span>
            ))}
          </div>
        </div>
      )}
      {m.trades && m.trades.length > 0 && (
        <details className="mt-3 rounded-lg bg-slate-800/30 ring-1 ring-white/5">
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-300">Ver {Math.min(m.trades.length, 20)} trades simulados (de {m.n_trades})</summary>
          <div className="max-h-64 overflow-y-auto px-2 pb-2">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-slate-800 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-2 py-1">Hora</th><th>Side</th><th>Entry</th><th>PnL</th><th>Salida</th></tr></thead>
              <tbody>{m.trades.slice(0,20).map((t,i) => (
                <tr key={i} className="border-t border-white/5"><td className="px-2 py-1 font-mono text-slate-400">{t.time.slice(11,16)}</td><td className={t.side==="buy" ? "text-emerald-400" : "text-rose-400"}>{t.side}</td><td className="font-mono">{t.entry.toFixed(2)}</td><td className={`font-mono ${t.pnl>=0?"text-emerald-400":"text-rose-400"}`}>{t.pnl>=0?"+":""}${t.pnl.toFixed(0)}</td><td className="text-slate-400">{t.close_reason}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
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
