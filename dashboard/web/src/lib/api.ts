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
  strategy?: string;
  strategy_name?: string;
  error?: string;
  n_trades?: number;
  periodo_dias?: number;
  trades_por_dia?: number;
  pnl_neto?: number;
  retorno_pct?: number;
  win_rate_pct?: number;
  profit_factor?: number;
  expectancy?: number;
  payoff_ratio?: number;
  sharpe_anual?: number;
  sortino_anual?: number;
  max_drawdown_pct?: number;
  veredicto?: string;
  daily?: [string, number][];
  rejections?: Record<string, number>;
  trades?: Array<{time:string;symbol:string;side:string;entry:number;sl:number;tp:number;close:number|null;close_reason:string;pnl:number;volume:number;strategy:string}>;
  gross_profit?: number;
  gross_loss?: number;
  costos_totales?: number;
}

export interface WindowRow {
  label: string;
  equity_final: number;
  pnl: number;
  retorno_pct: number;
}

// ===== Demo Wyckoff Types =====
export interface WyckoffPhase {
  phase: string;
  confidence: number;
  details: string;
}

export interface ConfluenceZone {
  price: number;
  is_low: boolean;
  is_high: boolean;
  strength: number;
  session_count: number;
  sessions: string[];
}

export interface SweepEvent {
  level: number;
  direction: string;
  penetration_pips: number;
  wick_ratio: number;
  candles_to_reclaim: number;
  volume_spike: number;
  timestamp: string;
}

export interface SignalEvent {
  direction: string;
  entry_price: number;
  sl_price: number;
  tp_price: number;
  sl_pips: number;
  tp_pips: number;
  confidence: number;
  timestamp: string;
  validation: unknown;
}

export interface VolumeDivergence {
  divergence_detected: boolean;
  events: Array<{
    zone_price: number;
    type: string;
    volume_ratio: number;
    price_change_pips: number;
    timestamp: string;
    interpretation: string;
  }>;
}

export interface SessionLevelsData {
  london_high: number;
  london_low: number;
  ny_high: number;
  ny_low: number;
  asia_high: number;
  asia_low: number;
  kill_zone_high: number;
  kill_zone_low: number;
}

export interface MacroStructure {
  trend: string;
  bos_levels: Array<{price: number; direction: string; time: string}>;
  choch_levels: Array<{price: number; direction: string; time: string}>;
  swing_highs: number[];
  swing_lows: number[];
}

export interface WyckoffAnalysisResponse {
  symbol: string;
  timeframe_analysis: {
    macro: MacroStructure;
    wyckoff: WyckoffPhase;
    setup_zone: {
      price: number;
      is_low: boolean;
      is_high: boolean;
      strength: number;
      session_count: number;
      sessions: string[];
    } | null;
    confluence_zones: ConfluenceZone[];
    detected_sweeps: SweepEvent[];
    signals: SignalEvent[];
    volume_divergence: VolumeDivergence;
    session_levels: SessionLevelsData;
  };
}

export interface CustomBacktestParams {
  symbol: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  risk_pct: number;
  rr_ratio: number;
  max_concurrent: number;
  breakeven_enabled: boolean;
  partials_enabled: boolean;
  partial_at_pct: number;
  partial_close_fraction: number;
  kill_switch_daily: number;
  kill_switch_monthly: number;
  sl_pips: number;
  wick_ratio_min: number;
  max_penetration_atr: number;
  volume_spike_mult: number;
  news_guard_enabled: boolean;
}

export interface CustomBacktestResponse {
  symbol: string;
  n_trades: number;
  pnl_neto: number;
  retorno_pct: number;
  win_rate_pct: number;
  profit_factor: number;
  sharpe_anual: number;
  max_drawdown_pct: number;
  daily: [string, number][];
  trades: Array<{
    entry_time: string;
    exit_time: string | null;
    direction: string;
    entry_price: number;
    exit_price: number | null;
    pnl_usd: number;
    pnl_pct: number;
    exit_reason: string;
    duration_min: number;
    sl_pips: number;
    tp_pips: number;
  }>;
  rejections: Record<string, number>;
  error?: string;
}

export interface ConfigDefaultsResponse {
  risk: {
    risk_pct_per_trade: number;
    rr_ratio: number;
    sl_pips: Record<string, number>;
    breakeven_enabled: boolean;
    breakeven_trigger_pct: number;
    partials_enabled: boolean;
    partial_stages: Array<{at_pct: number; close_fraction: number}>;
    max_concurrent: number;
    max_daily_loss: number;
    max_monthly_loss: number;
    max_consecutive_losses: number;
    wick_ratio_min: number;
    max_penetration_atr: number;
    volume_spike_mult: number;
    news_guard: boolean;
  };
  instruments: Record<string, {pip_size: number; pip_value: number; spread_pips: number}>;
  sessions: {
    timezone: string;
    sessions: Record<string, {start: string; end: string}>;
  };
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

export async function fetchBacktest(symbol: string, strategy: string = "v4"): Promise<BacktestMetrics> {
  const r = await fetch(`${BASE}/api/backtest/${symbol}?strategy=${strategy}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchEquity(symbol: string, window: string, strategy: string = "v4"): Promise<{ symbol: string; window: string; strategy: string; rows: WindowRow[] }> {
  const r = await fetch(`${BASE}/api/equity/${symbol}/${window}?strategy=${strategy}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchStrategies(): Promise<{strategies:string[];default:string}> {
  const r = await fetch(`${BASE}/api/strategies`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

// ===== Demo Wyckoff API =====
export async function fetchWyckoffAnalysis(symbol: string, lookbackDays: number = 30, minSessions: number = 2): Promise<WyckoffAnalysisResponse> {
  const r = await fetch(`${BASE}/api/demo/wyckoff/${symbol}?lookback_days=${lookbackDays}&min_sessions=${minSessions}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchCustomBacktest(params: CustomBacktestParams): Promise<CustomBacktestResponse> {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    searchParams.append(key, String(value));
  });
  const r = await fetch(`${BASE}/api/demo/backtest/custom?${searchParams.toString()}`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}

export async function fetchConfigDefaults(): Promise<ConfigDefaultsResponse> {
  const r = await fetch(`${BASE}/api/demo/config/defaults`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}
