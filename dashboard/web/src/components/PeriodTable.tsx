"use client";

import { useEffect, useState } from "react";
import { fetchEquity, WindowRow } from "@/lib/api";

const WINDOWS = [
  { key: "dia", label: "Día" },
  { key: "semana", label: "Semana" },
  { key: "mes", label: "Mes" },
  { key: "trimestre", label: "Trimestre" },
  { key: "ano", label: "Año" },
];

export function PeriodTable({ symbol }: { symbol: string }) {
  const [win, setWin] = useState("mes");
  const [rows, setRows] = useState<WindowRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchEquity(symbol, win)
      .then((d) => alive && setRows(d.rows))
      .catch(() => alive && setRows([]))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [symbol, win]);

  const pos = rows.filter((r) => r.pnl >= 0).length;
  const neg = rows.length - pos;

  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-white/5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">Evolución · {symbol}</h3>
        <div className="flex gap-1 rounded-lg bg-slate-800/60 p-1">
          {WINDOWS.map((w) => (
            <button
              key={w.key}
              onClick={() => setWin(w.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                win === w.key ? "bg-emerald-500/20 text-emerald-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex gap-4 text-[11px] text-slate-500">
        <span>{rows.length} periodos</span>
        <span className="text-emerald-400">▲ {pos} ganados</span>
        <span className="text-rose-400">▼ {neg} perdidos</span>
      </div>

      <div className="mt-3 max-h-64 overflow-y-auto rounded-lg bg-slate-800/30 ring-1 ring-white/5">
        <table className="w-full text-right text-xs">
          <thead className="sticky top-0 bg-slate-800/80 text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2 text-left">Periodo</th>
              <th className="px-3 py-2">P&L</th>
              <th className="px-3 py-2">Retorno</th>
              <th className="px-3 py-2">Equity</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-slate-500">cargando…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-slate-500">sin datos</td></tr>
            )}
            {!loading && rows.map((r) => (
              <tr key={r.label} className="border-t border-white/5">
                <td className="px-3 py-1.5 text-left text-slate-300">{r.label}</td>
                <td className={`px-3 py-1.5 font-mono tabular-nums ${r.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {r.pnl >= 0 ? "+" : ""}{r.pnl.toFixed(0)}
                </td>
                <td className={`px-3 py-1.5 font-mono tabular-nums ${r.retorno_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {r.retorno_pct >= 0 ? "+" : ""}{r.retorno_pct.toFixed(2)}%
                </td>
                <td className="px-3 py-1.5 font-mono tabular-nums text-slate-300">{r.equity_final.toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
