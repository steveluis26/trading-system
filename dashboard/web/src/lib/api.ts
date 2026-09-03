// Tipos del panel (Caso A: solo lectura)
export interface PanelSnapshot {
  symbol: string;
  time: string;
  price: number;
  tendencia_macro: "ALCISTA" | "BAJISTA" | "LATERAL" | "—";
  tendencia_detail: string;
  flujo_pct_comprador: number;
  flujo_label: "COMPRA" | "VENTA" | "EQUILIBRIO";
  volumen_5v: number;
  volumen_rel: number;
  atr: number;
  atr_regime: string;
  liquidez_arriba: number;
  liquidez_abajo: number;
  liquidez_detalle: string;
  error?: string;
}

export interface BacktestMetrics {
  symbol?: string;
  error?: string;
  n_trades?: number;
  periodo_dias?: number;
  pnl_neto?: number;
  win_rate_pct?: number;
  profit_factor?: number;
  expectancy?: number;
  sharpe_anual?: number;
  max_drawdown_pct?: number;
  veredicto?: string;
  daily?: [string, number][];
  rejections?: Record<string, number>;
}

export interface WindowRow {
  label: string;
  equity_final: number;
  pnl: number;
  retorno_pct: number;
}

const BASE = process.env.NEXT_PUBLIC_API || "http://127.0.0.1:8000";

export async function fetchPanels(): Promise<Record<string, PanelSnapshot>> {
  const r = await fetch(`${BASE}/api/panels`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchBacktest(symbol: string): Promise<BacktestMetrics> {
  const r = await fetch(`${BASE}/api/backtest/${symbol}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchEquity(symbol: string, window: string): Promise<{ symbol: string; window: string; rows: WindowRow[] }> {
  const r = await fetch(`${BASE}/api/equity/${symbol}/${window}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}
