"use client";

import { useEffect, useState } from "react";
import { fetchPanels, fetchBacktest, PanelSnapshot, BacktestMetrics } from "@/lib/api";
import { PairCard } from "@/components/PairCard";
import { BacktestCard } from "@/components/BacktestCard";
import { PeriodTable } from "@/components/PeriodTable";

const SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"];

export default function Home() {
  const [panels, setPanels] = useState<Record<string, PanelSnapshot>>({});
  const [bt, setBt] = useState<Record<string, BacktestMetrics | null>>({});
  const [updated, setUpdated] = useState<string>("");

  async function refresh() {
    try {
      const p = await fetchPanels();
      setPanels(p);
      setUpdated(new Date().toLocaleTimeString("es-MX"));
    } catch { /* mantener último estado */ }
  }

  async function loadBt() {
    const out: Record<string, BacktestMetrics | null> = {};
    for (const s of [...SYMBOLS, "ALL"]) {
      try { out[s] = await fetchBacktest(s); } catch { out[s] = null; }
    }
    setBt(out);
  }

  useEffect(() => {
    refresh();
    loadBt();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen bg-[radial-gradient(ellipse_at_top,#0b1220_0%,#060912_60%)] text-slate-200">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="flex items-end justify-between border-b border-white/5 pb-6">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-xs font-medium uppercase tracking-[0.2em] text-emerald-400/80">Live</span>
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-white">Panel de Estrategia SMC</h1>
            <p className="mt-1 text-sm text-slate-400">Contexto multi-timeframe en tiempo real · Caso A (solo lectura)</p>
          </div>
          <div className="text-right text-xs text-slate-500">
            <div>Actualizado {updated || "—"}</div>
            <div className="mt-0.5">EURUSD · GBPUSD · XAUUSD</div>
          </div>
        </header>

        <section className="mt-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Contexto en tiempo real</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {SYMBOLS.map((s) => <PairCard key={s} symbol={s} p={panels[s] ?? null} />)}
          </div>
        </section>

        <section className="mt-10">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Backtest por par (datos reales · veredicto honesto)</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {SYMBOLS.map((s) => <BacktestCard key={s} symbol={s} m={bt[s] ?? null} />)}
          </div>
        </section>

        <section className="mt-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Total conjunto (3 pares)</h2>
          <BacktestCard symbol="ALL" m={bt["ALL"] ?? null} />
        </section>

        <section className="mt-10">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Evolución por periodo</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {[...SYMBOLS, "ALL"].map((s) => <PeriodTable key={s} symbol={s} />)}
          </div>
        </section>

        <footer className="mt-10 border-t border-white/5 pt-6 text-[11px] leading-relaxed text-slate-600">
          SMC (Smart Money Concepts): sesgo D1 → impulso H1 → barrido de liquidez M15 → BOS M5.
          El flujo VSA es una estimación (sin order book real en forex retail). El veredicto exige
          ≥100 operaciones y ≥250 días para no calificar como ruido estadístico. Backtest sobre datos
          reales evtradelabs (2020–2026, spread real por vela).
        </footer>
      </div>
    </main>
  );
}
