# SMC Rules - Reglas Ejecutables para Backtester (Fase 1)

**Derivado de**: `docs/ESPECIFICACION_SMC.md` (completa, sin ambigüedades)  
**Objetivo**: Código determinista, testeable, sin interpretación — cada regla tiene fórmula exacta  
**Formato**: Pseudocódigo + fórmulas + parámetros configurables → implementable directo en Python

---

## 0. Constantes y Configuración Global

```python
# config/instruments.yaml
INSTRUMENTS = {
    "XAUUSD": {"pip_value_per_lot": 1.0, "contract_size": 100, "digits": 2},
    "EURUSD": {"pip_value_per_lot": 10.0, "contract_size": 100000, "digits": 5},
    "GBPUSD": {"pip_value_per_lot": 10.0, "contract_size": 100000, "digits": 5},
}

# config/sessions.yaml (horarios México UTC-6/UTC-5 DST)
SESSIONS = {
    "ASIA":   {"start": "18:00", "end": "03:00", "next_day": True},   # 18:00-03:00
    "LONDON": {"start": "02:00", "end": "11:00", "next_day": False},  # 02:00-11:00
    "NEWYORK": {"start": "07:00", "end": "16:00", "next_day": False}, # 07:00-16:00
}

# config/risk.yaml (parámetros clave)
RISK_CONFIG = {
    "lot_sizing": {"mode": "pct_risk", "risk_pct_per_trade": 0.01},
    "risk_reward": {"ratio": 2.0},
    "breakeven": {"enabled": True, "trigger_pct_of_tp": 0.40},
    "partials": {"enabled": True, "stages": [{"at_pct_of_tp": 0.40, "close_fraction": 0.33}]},
    "limits": {
        "max_concurrent_trades": 2,
        "max_daily_trades": 5,
        "daily_loss_limit_pct": 0.05,
        "monthly_loss_limit_pct": 0.30,
        "max_consecutive_losses": 5,
        "reactivation": "manual_only",
        "scope": "per_account"
    },
    "session_filters": {
        "avoid_friday_afternoon": True,
        "avoid_weekends": True,
        "avoid_high_impact_usd_news": True
    },
    "rejection_validation": {
        "atr_period": 14,
        "max_penetration_atr": 1.0,
        "min_wick_ratio": 0.50,
        "max_candles_to_reclaim": 2,
        "require_volume_spike": True
    },
    "entry_trigger": {
        "type": "market",
        "double_cross_required": True
    }
}
```

---

## 1. Cálculo de Niveles de Sesión (Session Levels)

### 1.1 Conversión de Zona Horaria
```python
def convert_to_mexico_time(utc_timestamp: pd.Timestamp) -> pd.Timestamp:
    """
    MT5 server time → México (UTC-6 estándar, UTC-5 con DST).
    Usar pytz/zoneinfo con 'America/Mexico_City'.
    """
    mexico_tz = ZoneInfo("America/Mexico_City")
    return utc_timestamp.tz_convert(mexico_tz)
```

### 1.2 High/Low por Sesión
```python
def calculate_session_levels(candles: pd.DataFrame, date: datetime.date) -> Dict[str, Dict]:
    """
    Input: DataFrame con columnas [timestamp, open, high, low, close, tick_volume] en tiempo México
    Output: Dict con High/Low de cada sesión para esa fecha
    
    Sesiones que cruzan medianoche (ASIA 18:00-03:00):
    - ASIA de fecha D = velas desde D-1 18:00 hasta D 03:00
    - LONDON de fecha D = velas desde D 02:00 hasta D 11:00
    - NEWYORK de fecha D = velas desde D 07:00 hasta D 16:00
    """
    mexico_candles = candles.copy()
    mexico_candles["mexico_time"] = mexico_candles["timestamp"].apply(convert_to_mexico_time)
    
    levels = {}
    
    # ASIA: D-1 18:00 → D 03:00
    asia_start = pd.Timestamp.combine(date - timedelta(days=1), time(18, 0), tzinfo=mexico_tz)
    asia_end = pd.Timestamp.combine(date, time(3, 0), tzinfo=mexico_tz)
    asia_candles = mexico_candles[(mexico_candles["mexico_time"] >= asia_start) & 
                                   (mexico_candles["mexico_time"] < asia_end)]
    levels["ASIA"] = {
        "high": asia_candles["high"].max() if len(asia_candles) else None,
        "low": asia_candles["low"].min() if len(asia_candles) else None,
        "start": asia_start, "end": asia_end
    }
    
    # LONDON: D 02:00 → D 11:00
    lon_start = pd.Timestamp.combine(date, time(2, 0), tzinfo=mexico_tz)
    lon_end = pd.Timestamp.combine(date, time(11, 0), tzinfo=mexico_tz)
    lon_candles = mexico_candles[(mexico_candles["mexico_time"] >= lon_start) & 
                                  (mexico_candles["mexico_time"] < lon_end)]
    levels["LONDON"] = {
        "high": lon_candles["high"].max() if len(lon_candles) else None,
        "low": lon_candles["low"].min() if len(lon_candles) else None,
        "start": lon_start, "end": lon_end
    }
    
    # NEWYORK: D 07:00 → D 16:00
    ny_start = pd.Timestamp.combine(date, time(7, 0), tzinfo=mexico_tz)
    ny_end = pd.Timestamp.combine(date, time(16, 0), tzinfo=mexico_tz)
    ny_candles = mexico_candles[(mexico_candles["mexico_time"] >= ny_start) & 
                                 (mexico_candles["mexico_time"] < ny_end)]
    levels["NEWYORK"] = {
        "high": ny_candles["high"].max() if len(ny_candles) else None,
        "low": ny_candles["low"].min() if len(ny_candles) else None,
        "start": ny_start, "end": ny_end
    }
    
    return levels
```

### 1.3 Zona de Confluencia (Fractal)
```python
def detect_confluence_zones(session_levels: Dict, tolerance_pips: float = 10.0) -> List[Dict]:
    """
    Detecta niveles donde 2-3 sesiones coinciden en precio (±tolerancia).
    Retorna lista de zonas con: price_level, sessions_involved, strength (2 or 3).
    """
    all_levels = []
    for sess_name, data in session_levels.items():
        if data["high"]: all_levels.append(("HIGH", sess_name, data["high"]))
        if data["low"]: all_levels.append(("LOW", sess_name, data["low"]))
    
    zones = []
    for i, (type1, sess1, price1) in enumerate(all_levels):
        coinciding = [(type1, sess1, price1)]
        for type2, sess2, price2 in all_levels[i+1:]:
            if sess1 != sess2 and abs(price1 - price2) <= tolerance_pips * 0.0001:  # ajustar por instrumento
                coinciding.append((type2, sess2, price2))
        
        if len(coinciding) >= 2:
            avg_price = sum(p for _, _, p in coinciding) / len(coinciding)
            zones.append({
                "price": avg_price,
                "sessions": [s for _, s, _ in coinciding],
                "types": [t for t, _, _ in coinciding],
                "strength": len(coinciding),  # 2 o 3
                "is_high": all(t == "HIGH" for t, _, _ in coinciding),
                "is_low": all(t == "LOW" for t, _, _ in coinciding)
            })
    
    # Deduplicar zonas solapadas
    return merge_overlapping_zones(zones, tolerance_pips)
```

---

## 2. Análisis de Estructura Macro (1D/4H/1H)

### 2.1 Detección HH/HL/LH/LL
```python
def analyze_market_structure(candles_1d: pd.DataFrame, lookback: int = 50) -> Dict:
    """
    Detecta tendencia en 1D usando pivotes de sesión (no conteo velas).
    Usa High/Low de sesiones como pivotes objetivos.
    """
    # Obtener niveles de sesión para cada día en lookback
    daily_levels = []
    for date in candles_1d["date"].unique()[-lookback:]:
        levels = calculate_session_levels(candles_1d, date)
        daily_levels.append({"date": date, **levels})
    
    # Extraer secuencia de Highs y Lows significativos
    highs = [(d["date"], d["LONDON"]["high"]) for d in daily_levels if d["LONDON"]["high"]]
    lows = [(d["date"], d["LONDON"]["low"]) for d in daily_levels if d["LONDON"]["low"]]
    
    # Clasificar últimos 3-4 pivotes
    structure = {"trend": "NEUTRAL", "last_bos": None, "pivots": []}
    
    if len(highs) >= 3 and len(lows) >= 3:
        # HH/HL = alcista; LH/LL = bajista
        last_highs = [h[1] for h in highs[-3:]]
        last_lows = [l[1] for l in lows[-3:]]
        
        higher_highs = all(last_highs[i] < last_highs[i+1] for i in range(len(last_highs)-1))
        higher_lows = all(last_lows[i] < last_lows[i+1] for i in range(len(last_lows)-1))
        lower_highs = all(last_highs[i] > last_highs[i+1] for i in range(len(last_highs)-1))
        lower_lows = all(last_lows[i] > last_lows[i+1] for i in range(len(last_lows)-1))
        
        if higher_highs and higher_lows:
            structure["trend"] = "BULLISH"
        elif lower_highs and lower_lows:
            structure["trend"] = "BEARISH"
        else:
            structure["trend"] = "RANGING"
    
    return structure
```

### 2.2 BOS/CHoCH en 4H/1H (Confirmación)
```python
def detect_bos_choch(candles_4h: pd.DataFrame, macro_trend: str, key_level: float) -> Optional[Dict]:
    """
    Detecta Break of Structure en 4H/1H que confirma dirección macro.
    key_level = High/Low de sesión relevante (confluencia).
    """
    # Buscar vela que rompa y cierre claramente el nivel clave
    for idx, row in candles_4h.iterrows():
        if macro_trend == "BULLISH":
            # Buscar rompimiento de Low previo (CHoCH a bajista) o confirmación High
            if row["close"] > key_level and row["open"] < key_level:
                return {"type": "BOS_BULLISH", "timestamp": idx, "level": key_level, "candle": row}
        elif macro_trend == "BEARISH":
            if row["close"] < key_level and row["open"] > key_level:
                return {"type": "BOS_BEARISH", "timestamp": idx, "level": key_level, "candle": row}
    return None
```

---

## 3. Setup Detector (15M)

### 3.1 Identificación de Zona de Interés
```python
def find_setup_zone(candles_15m: pd.DataFrame, session_levels: Dict, macro_trend: str) -> Optional[Dict]:
    """
    Busca zona de confluencia (2-3 sesiones) en dirección de tendencia macro.
    Retorna zona candidata o None.
    """
    confluence_zones = detect_confluence_zones(session_levels)
    
    for zone in confluence_zones:
        # Filtrar por dirección de tendencia macro
        if macro_trend == "BULLISH" and zone["is_low"]:
            # Zona de soporte confluente para compra
            return {"zone": zone, "direction": "LONG", "entry_level": zone["price"]}
        elif macro_trend == "BEARISH" and zone["is_high"]:
            # Zona de resistencia confluente para venta
            return {"zone": zone, "direction": "SHORT", "entry_level": zone["price"]}
    
    return None
```

### 3.2 Detección de Barrido (Sweep)
```python
def detect_sweep(candles_5m: pd.DataFrame, zone: Dict, direction: str) -> Optional[Dict]:
    """
    Detecta barrido de liquidez en 5M: precio perfora nivel de zona y regresa.
    direction: "LONG" = barrido de soporte (low) → regreso arriba
               "SHORT" = barrido de resistencia (high) → regreso abajo
    """
    level = zone["entry_level"]
    
    for i in range(1, len(candles_5m)):
        prev = candles_5m.iloc[i-1]
        curr = candles_5m.iloc[i]
        
        if direction == "LONG":
            # Barrido: low previo rompe nivel, vela actual cierra arriba del nivel
            swept = prev["low"] < level
            reclaimed = curr["close"] > level
        else:  # SHORT
            swept = prev["high"] > level
            reclaimed = curr["close"] < level
        
        if swept and reclaimed:
            return {
                "sweep_candle": prev,
                "reclaim_candle": curr,
                "sweep_index": i-1,
                "reclaim_index": i,
                "level": level,
                "direction": direction
            }
    
    return None
```

---

## 4. Trigger Engine - **CORE REGLAS EXACTAS** (§4.1-4.4 ESPECIFICACION)

### 4.1 Validación de Rechazo - 3 Condiciones Mecánicas (TODAS requeridas)

```python
def validate_rejection(sweep: Dict, candles_5m: pd.DataFrame, atr_value: float, 
                       config: Dict) -> Tuple[bool, str]:
    """
    Valida las 3 condiciones mecánicas de rechazo.
    Retorna (es_valido, razon_si_no).
    
    Config keys: atr_period, max_penetration_atr, min_wick_ratio, max_candles_to_reclaim
    """
    sweep_candle = sweep["sweep_candle"]
    reclaim_candle = sweep["reclaim_candle"]
    level = sweep["level"]
    direction = sweep["direction"]
    
    # --- CONDICIÓN 1: Profundidad Máxima (ATR Filter) ---
    if direction == "LONG":
        penetration = level - sweep_candle["low"]  # pips abajo del nivel
    else:
        penetration = sweep_candle["high"] - level  # pips arriba del nivel
    
    max_allowed_penetration = atr_value * config["max_penetration_atr"]
    
    if penetration > max_allowed_penetration:
        return False, f"Penetración {penetration:.1f} pips > 1 ATR ({max_allowed_penetration:.1f}) = rompimiento real"
    
    # --- CONDICIÓN 2: Anatomía de la Vela (Mecha ≥ 50% FIJO) ---
    candle_range = sweep_candle["high"] - sweep_candle["low"]
    if candle_range == 0:
        return False, "Rango de vela = 0"
    
    if direction == "LONG":
        # Mecha inferior = distancia desde low hasta min(open, close)
        lower_wick = min(sweep_candle["open"], sweep_candle["close"]) - sweep_candle["low"]
        wick_ratio = lower_wick / candle_range
    else:
        # Mecha superior = distancia desde max(open, close) hasta high
        upper_wick = sweep_candle["high"] - max(sweep_candle["open"], sweep_candle["close"])
        wick_ratio = upper_wick / candle_range
    
    if wick_ratio < config["min_wick_ratio"]:
        return False, f"Mecha ratio {wick_ratio:.2f} < {config['min_wick_ratio']} (mín 50% FIJO)"
    
    # --- CONDICIÓN 3: Factor Tiempo (Reclaim en ≤ 2 VELAS MÁXIMO) ---
        sweep_idx = sweep["sweep_index"]
        reclaim_idx = sweep["reclaim_index"]
        candles_to_reclaim = reclaim_idx - sweep_idx
    
        if candles_to_reclaim > config["max_candles_to_reclaim"]:
            return False, f"Reclaim tomó {candles_to_reclaim} velas > {config['max_candles_to_reclaim']} (máx 2) = aceptación precio = momentum perdido"
    
        # Validación adicional: cuerpo de vela reclaim debe cerrar DEL LADO CORRECTO del nivel
        if direction == "LONG":
            if reclaim_candle["close"] <= level:
                return False, "Vela reclaim no cierra cuerpo arriba del nivel"
        else:
            if reclaim_candle["close"] >= level:
                return False, "Vela reclaim no cierra cuerpo abajo del nivel"
    
        return True, "Rechazo válido - 3 condiciones cumplidas (mecha ≥50% FIJO, reclaim ≤2 velas)"
```

### 4.2 Confirmación de Volumen (Absorción)
```python
def confirm_volume_absorption(sweep_candle: pd.Series, recent_candles: pd.DataFrame, 
                              volume_multiplier: float = 1.5) -> bool:
    """
    La vela del barrido (sweep_candle) debe tener tick_volume > volume_multiplier × media reciente.
    recent_candles: últimas 20 velas excluyendo la sweep_candle.
    """
    avg_volume = recent_candles["tick_volume"].mean()
    return sweep_candle["tick_volume"] >= avg_volume * volume_multiplier
```

### 4.3 Gatillo de Entrada (Double Cross - Market Order)
```python
def check_entry_trigger(candles_5m: pd.DataFrame, sweep: Dict, 
                        validated_rejection: bool, volume_confirmed: bool) -> Optional[Dict]:
    """
    La entrada SOLO se dispara si:
    1. Rechazo validado (3 condiciones)
    2. Volumen confirmado
    3. DOBLE CRUCE: precio ya cruzó de regreso (reclaim) → ese cruce ES la entrada
    
    Retorna señal de entrada o None.
    """
    if not (validated_rejection and volume_confirmed):
        return None
    
    # El cruce de reclaim YA ocurrió en la vela de reclaim
    # Entrada = mercado en apertura de vela SIGUIENTE al reclaim
    reclaim_idx = sweep["reclaim_index"]
    entry_idx = reclaim_idx + 1
    
    if entry_idx >= len(candles_5m):
        return None  # No hay vela siguiente aún
    
    entry_candle = candles_5m.iloc[entry_idx]
    direction = sweep["direction"]
    
    return {
        "signal": "ENTRY",
        "direction": direction,  # "LONG" o "SHORT"
        "entry_price": entry_candle["open"],  # Market order al open siguiente
        "entry_time": entry_candle["timestamp"],
        "trigger_level": sweep["level"],
        "sweep_candle": sweep["sweep_candle"],
        "reclaim_candle": sweep["reclaim_candle"],
        "validation": {
            "atr_filter": True,
            "wick_ratio": True,
            "time_reclaim": True,
            "volume_spike": True
        }
    }
```

---

## 5. Position Sizing (1% Riesgo Dinámico)

```python
def calculate_lot_size(balance: float, sl_pips: float, symbol: str, 
                       risk_pct: float = 0.01) -> float:
    """
    Lote = (Balance × risk_pct) / (SL_pips × Valor_Pip_Por_Lote)
    Redondeado a step del broker (ej. 0.01 para XAUUSD).
    """
    pip_value = INSTRUMENTS[symbol]["pip_value_per_lot"]
    risk_amount = balance * risk_pct
    raw_lot = risk_amount / (sl_pips * pip_value)
    
    # Redondear a step del broker (0.01 para la mayoría)
    step = 0.01
    return round(raw_lot / step) * step
```

---

## 6. Stop Loss & Take Profit (R:R 1:2 Fijo)

```python
def calculate_sl_tp(entry_price: float, direction: str, sl_pips: float, 
                    rr_ratio: float = 2.0) -> Tuple[float, float]:
    """
    SL = distancia fija en pips desde entry
    TP = SL_pips × rr_ratio
    """
    pip_size = 0.01 if "XAU" in symbol else 0.0001  # ajustar por símbolo
    
    if direction == "LONG":
        sl = entry_price - (sl_pips * pip_size)
        tp = entry_price + (sl_pips * rr_ratio * pip_size)
    else:
        sl = entry_price + (sl_pips * pip_size)
        tp = entry_price - (sl_pips * rr_ratio * pip_size)
    
    return round(sl, 5), round(tp, 5)
```

---

## 7. Gestión de Posición (Breakeven + Parciales al 40%)

```python
class PositionManager:
    def __init__(self, config: Dict):
        self.breakeven_pct = config["breakeven"]["trigger_pct_of_tp"]  # 0.40
        self.partials = config["partials"]["stages"]  # [{at_pct: 0.40, close_fraction: 0.33}]
        self.partial_executed = set()
    
    def check_breakeven(self, position: Dict, current_price: float) -> Optional[float]:
        """
        Si precio avanzó 40% del camino al TP → mover SL a breakeven (entry_price).
        Retorna nuevo SL o None.
        """
        entry = position["entry_price"]
        tp = position["tp"]
        sl = position["sl"]
        direction = position["direction"]
        
        if direction == "LONG":
            distance_to_tp = tp - entry
            current_progress = current_price - entry
        else:
            distance_to_tp = entry - tp
            current_progress = entry - current_price
        
        if distance_to_tp > 0 and current_progress / distance_to_tp >= self.breakeven_pct:
            return entry  # Breakeven = entry price
        
        return None
    
    def check_partials(self, position: Dict, current_price: float) -> List[Dict]:
        """
        Revisa cada etapa de parciales. Retorna lista de {close_fraction, reason}.
        """
        actions = []
        entry = position["entry_price"]
        tp = position["tp"]
        direction = position["direction"]
        current_lot = position["current_lot"]
        
        distance_to_tp = abs(tp - entry)
        if direction == "LONG":
            current_progress = current_price - entry
        else:
            current_progress = entry - current_price
        
        if distance_to_tp <= 0:
            return actions
        
        progress_pct = current_progress / distance_to_tp
        
        for i, stage in enumerate(self.partials):
            if i in self.partial_executed:
                continue
            if progress_pct >= stage["at_pct_of_tp"]:
                close_lot = current_lot * stage["close_fraction"]
                actions.append({
                    "action": "PARTIAL_CLOSE",
                    "lot": round(close_lot, 2),
                    "reason": f"Partial at {stage['at_pct_of_tp']*100}% TP"
                })
                self.partial_executed.add(i)
        
        return actions
```

---

## 8. Risk Engine (Filtro Inquebrantable - Pre-Ejecución)

```python
class RiskEngine:
    def __init__(self, config: Dict, account_state: Dict):
        self.config = config
        self.state = account_state  # {balance, equity, daily_pnl, monthly_pnl, 
                                    #  open_positions, daily_trades, consecutive_losses}
    
    def validate_pre_trade(self, signal: Dict, sl_pips: float) -> Tuple[bool, str]:
        """
        Ejecutar ANTES de cualquier orden. Si retorna False → orden BLOQUEADA.
        """
        limits = self.config["limits"]
        
        # 1. Max concurrent trades
        if len(self.state["open_positions"]) >= limits["max_concurrent_trades"]:
            return False, f"Max concurrent trades ({limits['max_concurrent_trades']}) reached"
        
        # 2. Max daily trades
        if self.state["daily_trades"] >= limits["max_daily_trades"]:
            return False, f"Max daily trades ({limits['max_daily_trades']}) reached"
        
        # 3. Daily loss limit
        daily_loss_pct = abs(self.state["daily_pnl"]) / self.state["balance"]
        if daily_loss_pct >= limits["daily_loss_limit_pct"]:
            return False, f"Daily loss limit ({limits['daily_loss_limit_pct']*100}%) reached"
        
        # 4. Monthly loss limit
        monthly_loss_pct = abs(self.state["monthly_pnl"]) / self.state["balance"]
        if monthly_loss_pct >= limits["monthly_loss_limit_pct"]:
            return False, f"Monthly loss limit ({limits['monthly_loss_limit_pct']*100}%) reached"
        
        # 5. Consecutive losses
        if self.state["consecutive_losses"] >= limits["max_consecutive_losses"]:
            return False, f"Max consecutive losses ({limits['max_consecutive_losses']}) reached"
        
        # 6. Session filters
        if self.config["session_filters"]["avoid_friday_afternoon"]:
            if self._is_friday_afternoon():
                return False, "Friday afternoon - no trading"
        
        if self.config["session_filters"]["avoid_weekends"]:
            if self._is_weekend():
                return False, "Weekend - no trading"
        
        if self.config["session_filters"]["avoid_high_impact_usd_news"]:
            if self._is_high_impact_news_soon():
                return False, "High impact USD news imminent"
        
        return True, "OK"
    
    def update_post_trade(self, result: Dict):
        """Actualizar estado tras cierre de operación."""
        self.state["daily_pnl"] += result["pnl"]
        self.state["monthly_pnl"] += result["pnl"]
        self.state["daily_trades"] += 1
        self.state["balance"] += result["pnl"]
        self.state["equity"] = self.state["balance"]  # simplificado
        
        if result["pnl"] < 0:
            self.state["consecutive_losses"] += 1
        else:
            self.state["consecutive_losses"] = 0
```

---

## 9. Filtros de Sesión / Noticias

```python
def is_trading_allowed_now(config: Dict, news_calendar: List[Dict]) -> Tuple[bool, str]:
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    
    # Viernes después de 17:00 México (cierre NY)
    if config["avoid_friday_afternoon"] and now.weekday() == 4 and now.hour >= 17:
        return False, "Friday afternoon"
    
    # Fines de semana
    if config["avoid_weekends"] and now.weekday() >= 5:
        return False, "Weekend"
    
    # Noticias USD alto impacto en próximas 2 horas
    if config["avoid_high_impact_usd_news"]:
        for event in news_calendar:
            if event["currency"] == "USD" and event["impact"] == "HIGH":
                event_time = event["datetime"].astimezone(ZoneInfo("America/Mexico_City"))
                if 0 <= (event_time - now).total_seconds() <= 7200:  # 2 horas
                    return False, f"High impact news: {event['name']} at {event_time}"
    
    return True, "OK"
```

---

## 10. Pipeline Completo de Backtest (Orquestación)

```python
def run_backtest(data: Dict[str, pd.DataFrame], config: Dict, 
                 initial_balance: float = 10000) -> Dict:
    """
    data: {"1D": df, "4H": df, "1H": df, "15M": df, "5M": df} todos en tiempo México
    Retorna: {trades: List, equity_curve: List, metrics: Dict}
    """
    account = {"balance": initial_balance, "equity": initial_balance, 
               "daily_pnl": 0, "monthly_pnl": 0,
               "open_positions": [], "daily_trades": 0, "consecutive_losses": 0}
    
    risk_engine = RiskEngine(config, account)
    position_mgr = PositionManager(config)
    
    trades = []
    equity_curve = []
    
    # Iterar día por día (para niveles de sesión)
    for date in sorted(data["1D"]["date"].unique()):
        # 1. Calcular niveles de sesión para este día
        session_levels = calculate_session_levels(data["5M"], date)
        
        # 2. Análisis macro (1D)
        macro = analyze_market_structure(data["1D"])
        if macro["trend"] == "RANGING":
            continue  # No operar en ranging
        
        # 3. Confirmación 4H/1H
        key_level = get_key_level_for_trend(session_levels, macro["trend"])
        bos = detect_bos_choch(data["4H"], macro["trend"], key_level)
        if not bos:
            continue  # Sin confirmación macro
        
        # 4. Buscar setup en 15M
        setup = find_setup_zone(data["15M"], session_levels, macro["trend"])
        if not setup:
            continue
        
        # 5. Detectar barrido en 5M
        sweep = detect_sweep(data["5M"], setup["zone"], setup["direction"])
        if not sweep:
            continue
        
        # 6. Calcular ATR(14) en 5M para validación
        atr_14 = calculate_atr(data["5M"], period=14, at_index=sweep["sweep_index"])
        
        # 7. Validar rechazo (3 condiciones)
        valid_rejection, reason = validate_rejection(sweep, data["5M"], atr_14, config["rejection_validation"])
        if not valid_rejection:
            continue
        
        # 8. Confirmar volumen
        recent_vol = data["5M"].iloc[max(0, sweep["sweep_index"]-20):sweep["sweep_index"]]
        vol_ok = confirm_volume_absorption(sweep["sweep_candle"], recent_vol)
        if not vol_ok:
            continue
        
        # 9. Generar señal de entrada
        entry_signal = check_entry_trigger(data["5M"], sweep, valid_rejection, vol_ok)
        if not entry_signal:
            continue
        
        # 10. Risk Engine - validar ANTES de entrar
        sl_pips = calculate_sl_pips(entry_signal, session_levels, config)  # basado en zona
        allowed, risk_reason = risk_engine.validate_pre_trade(entry_signal, sl_pips)
        if not allowed:
            continue  # Señal bloqueada por riesgo
        
        # 11. Calcular lote (1% riesgo)
        lot = calculate_lot_size(account["balance"], sl_pips, entry_signal["symbol"])
        
        # 12. Calcular SL/TP
        sl, tp = calculate_sl_tp(entry_signal["entry_price"], entry_signal["direction"], sl_pips)
        
        # 13. Simular posición hasta cierre
        trade_result = simulate_position(
            entry_signal, lot, sl, tp, data["5M"], position_mgr, config
        )
        
        # 14. Actualizar risk engine
        risk_engine.update_post_trade(trade_result)
        account = risk_engine.state
        
        trades.append(trade_result)
        equity_curve.append({"timestamp": trade_result["exit_time"], "equity": account["equity"]})
    
    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "metrics": calculate_metrics(trades, initial_balance)
    }
```

---

## 11. Tests Unitarios Requeridos (pytest)

```python
# tests/test_rejection_filters.py
def test_atr_filter_blocks_deep_penetration():
    """Penetración > 1 ATR → rechazo inválido"""
    sweep = make_sweep_candle(low=1000, level=1050)  # penetración 50 pips
    atr = 30  # 1 ATR = 30 pips
    assert not validate_rejection(sweep, ..., atr, config)[0]

def test_wick_ratio_requires_50pct():
    """Mecha < 50% rango → rechazo inválido (50% FIJO)"""
    candle = {"high": 1010, "low": 1000, "open": 1008, "close": 1006}  # mecha 2/10 = 20%
    assert not validate_rejection_anatomy(candle, "LONG", 0.50)[0]

def test_time_reclaim_max_2_candles():
    """Reclaim en 3ra vela → rechazo inválido (máx 2 velas)"""
    sweep = make_sweep_at_index(5)
    reclaim = make_reclaim_at_index(8)  # 3 velas después (índices 6,7,8 = 3 velas)
    assert not validate_time_reclaim(sweep, reclaim, max_candles=2)[0]

def test_double_cross_entry_trigger():
    """Entrada solo en cruce de regreso, market order"""
    signal = check_entry_trigger(...)
    assert signal["direction"] == "LONG"
    assert signal["entry_price"] == next_candle_open

def test_sizing_1pct_risk():
    """Lote calculado para arriesgar exactamente 1% del balance"""
    lot = calculate_lot_size(balance=10000, sl_pips=50, symbol="XAUUSD", risk_pct=0.01)
    # 1% de 10000 = $100 riesgo; 50 pips × $1/pip/lote = $50/lote → 2 lotes = 0.02
    assert lot == 0.02

def test_breakeven_at_40pct():
    """Breakeven se activa al 40% del camino al TP"""
    pos = {"entry": 1000, "tp": 1100, "sl": 950, "direction": "LONG"}
    mgr = PositionManager(config)
    # 40% de 100 pips = 40 pips → precio 1040
    new_sl = mgr.check_breakeven(pos, 1039)
    assert new_sl is None
    new_sl = mgr.check_breakeven(pos, 1040)
    assert new_sl == 1000
```

---

## 12. Métricas de Salida (Success Criteria Fase 1)

```python
def calculate_metrics(trades: List[Dict], initial_balance: float) -> Dict:
    if not trades:
        return {}
    
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    
    total_pnl = sum(t["pnl"] for t in trades)
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    
    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
        "net_profit": total_pnl,
        "net_profit_pct": total_pnl / initial_balance * 100,
        "max_drawdown_pct": calculate_max_dd(trades, initial_balance),
        "sharpe_ratio": calculate_sharpe(trades),
        "expectancy": total_pnl / len(trades),
        "avg_win": gross_profit / len(wins) if wins else 0,
        "avg_loss": gross_loss / len(losses) if losses else 0,
        "max_consecutive_wins": max_consecutive(trades, lambda t: t["pnl"] > 0),
        "max_consecutive_losses": max_consecutive(trades, lambda t: t["pnl"] <= 0),
        "risk_engine_blocks": count_risk_blocks(),  # tracking interno
        "setup_detection_rate": setups_found / total_days,
        "rejection_validation_pass_rate": validated / sweeps_detected
    }

# UMBRALES TERM SHEET (mínimos para pasar a Fase 2)
MIN_METRICS = {
    "profit_factor": 1.3,
    "max_drawdown_pct": 15.0,
    "sharpe_ratio": 1.0,
    "win_rate": 40.0,  # mínimo
}
```

---

**Fin de SMC_RULES.md** — Listo para implementar backtester Fase 1.