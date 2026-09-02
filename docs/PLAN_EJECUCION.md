# Plan de Ejecución - Trading System (AuraTrade Pro) — **ACTUALIZADO**

**Proyecto**: Plataforma algorítmica MT5 + ML para estrategia SMC de Mariely  
**Visión**: "Preservar capital = regla máxima" → Risk-first architecture  
**Arquitectura**: 4 Fases secuenciales + 4 Componentes desacoplados  
**Estado**: **FASE 1 LISTA PARA ARRANCAR** — Estrategia 100% especificada, CERO ambigüedades

---

## ARQUITECTURA ACORDADA CON MARIELY

### 4 Fases (Secuenciales, sin saltos)

| Fase | Objetivo | Entregable | Criterio de paso a siguiente |
|---|---|---|---|
| **1. Reglas + Backtesting** | Convertir estrategia a reglas codificables → probar contra años de historial **SIN riesgo** | `backtester/` + `results/` + `specs/SMC_RULES.md` | Backtest honesto muestra edge estadístico + reglas replican capturas de Mariely |
| **2. Conexión MT5 + Demo** | Ejecutor real conectado a MT5 en **cuenta demo** (no dinero real) | `executor/` + `config/mt5.yaml` + demo verificada | Órdenes se ejecutan correctamente en demo, SL/TP/lote calculados ok |
| **3. Risk Engine (Siempre activo)** | Filtro inquebrantable **antes** de cualquier ejecución — checa TODOS los límites | `risk_engine/` (librería independiente) | Zero operaciones que violen reglas en demo + stress tests |
| **4. Capa Avanzada** | Perfil de volumen, order flow, ML (redes neuronales) — **SOLO si base funciona** | `ml_layer/` + `volume_profile/` | Fase 1-3 estables + datos de volumen disponibles |

> **Principio**: "No construir algo complicado sobre base no comprobada"

---

### 4 Componentes (Separación de responsabilidades)

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  1. ESTRATEGIA      │────▶│  2. RIESGO          │────▶│  3. EJECUTOR        │────▶│  4. TABLERO         │
│  (Cerebro)          │     │  (Filtro)           │     │  (MT5)              │     │  (UI/Telegram)      │
│  • Lee mercado      │     │  • Valida TODAS     │     │  • Orden market     │     │  • Dashboard web    │
│  • Detecta setup    │     │    reglas riesgo    │     │  • Calcula lote     │     │  • P&L tiempo real  │
│  • Emite señal      │     │  • Bloquea si falla │     │  • Pone SL/TP       │     │  • Alertas Telegram │
│  • NO ejecuta       │     │  • Inquebrantable   │     │  • Gestiona pos.    │     │  • Reportes diario  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘     └─────────────────────┘
        │                           │                           │                           │
        ▼                           ▼                           ▼                           ▼
   signal:                    verdict:                    order:                      event:
   {dir, entry,               {allow: bool,             {symbol, lot,               {type, data,
    sl_pips,                   reason,                   sl, tp,                     timestamp}
    tp_pips,                   risk_pct}                 magic, comment}
    confidence}
```

**Contrato entre componentes**: Tipado estricto (Pydantic), sin acoplamiento — cada uno testeable en aislamiento.

---

## BLOQUEADORES EXTERNOS (Deben resolverse ANTES de Fase 2)

### 🏦 Broker (Vantage / VT Markets) — 3 Preguntas Críticas

| # | Pregunta | Por qué bloquea |
|---|---|---|
| **B1** | **Programa formal**: ¿MAM / PAMM / gestión de terceros cuál? ¿Documento/link oficial? | Define arquitectura multi-cuenta, compliance, legal |
| **B2** | **Conexión técnica**: ¿API directa / MetaApi / software autorizado? ¿Credenciales? | Define `executor/` implementation (MetaApi ~$15-30/cuenta/mes, rate limits) |
| **B3** | **Registro gestor**: ¿Requiere autorización/registro formal para operar cuentas ajenas? | Timeline legal, compliance antes de launch |

> **Acción**: Enviar cuestionario formal por escrito a ambos brokers. Guardar respuestas por escrito.

---

### ⚖️ Legal / Comercial — Term Sheet

| Clave | Definición necesaria |
|---|---|
| **Propiedad código** | 100% tú (usuario) — confirmar por escrito |
| **Revenue share** | % sobre ganancias netas (pendiente definir) |
| **Definición "funciona"** | Métrica objetiva: ej. "backtest 2 años: PF > 1.3, DD < 15%, Sharpe > 1.0" |
| **Comisión trailing** | % sobre volúmen o ganancias recurrentes |
| **Salida/terminación** | Cláusulas de salida, propiedad datos, no-competencia |

> **Acción**: Redactar term sheet simple (1-2 páginas), firmar antes de invertir semanas en desarrollo.

---

### 📊 Datos Históricos (Para Fase 1 Backtester)

| Requisito | Detalle |
|---|---|
| **Instrumentos** | XAUUSD, EURUSD, GBPUSD |
| **Timeframes** | 1D, 4H, 1H, 15M, 5M (mínimo) |
| **Profundidad** | Mínimo 2 años (ideal 5+) |
| **Formato** | CSV/Parquet: timestamp, open, high, low, close, tick_volume |
| **Fuente** | Pendiente definir: MT5 export, broker API, proveedor (TickData, Dukascopy, etc.) |
| **Zona horaria** | **México (UTC-6 / UTC-5 con DST)** — confirmado en ESPECIFICACION_SMC.md §13 |

> **Acción**: Definir fuente y descargar ANTES de escribir backtester.

---

## PENDIENTES CON MARIELY — **TODOS RESUELTOS** ✅

| # | Pregunta | **RESPUESTA** | Componente |
|---|---|---|---|
| **1** | Sizing | **1% riesgo/op (dinámico)** — `Lote = (Balance × 0.01) / (SL_pips × Valor_Pip)` | `executor.lot_calculator` |
| **2** | Breakeven/parciales | **40% del camino al TP** | `executor.position_manager` |
| **3** | Flechas agrupadas | **Referencias visuales únicamente** (no reentradas) | `strategy.entry_logic` |
| **4** | Manipulación buena vs mala | **3 filtros mecánicos** (§4.1-4.4 ESPECIFICACION_SMC.md) | `risk_engine.filters` |
| **5** | Confluencia peso | **SIEMPRE más peso** | `strategy.setup_scoring` |
| **6** | Rechazo válido | **3 condiciones** (ATR ≤1, mecha ≥50%, reclaim ≤2-3 velas) | `strategy.trigger` |
| **7** | Inyección capital | **Pico volumen en vela falso rompimiento + retorno** | `strategy.confirmation` |
| **8** | Zonas horarias | **México (UTC-6/UTC-5 DST)**, invisibles + visibles, fractal | `strategy.session_levels` |
| **9** | Límites agregados | **Por cuenta individual** | `risk_engine.limits` |
| **10** | Trendline diagonal | **Referencia ocasional**, visible, confirmación adicional | `strategy.bias` (opcional) |

---

## ROADMAP TÉCNICO (Post-bloqueadores externos)

### Fase 1: Backtester Honesto (4-6 semanas estimadas)

```
trading_system/
├── backtester/
│   ├── data_loader.py          # Carga CSV/Parquet, resamplea TFs, maneja zona horaria México
│   ├── session_calculator.py   # High/Low Asia/London/NY en huso México (UTC-6/UTC-5 DST)
│   ├── structure_analyzer.py   # HH/HL/LH/LL, BOS/CHoCH en macro (1D/4H/1H)
│   ├── setup_detector.py       # Confluencia (2-3 sesiones), barrido, acumulación
│   ├── trigger_engine.py       # 3 filtros mecánicos: cierre vela, double cross, volumen + 3 condiciones ATR/mecha/tiempo
│   ├── position_simulator.py   # SL/TP 1:2, breakeven 40%, parciales, sizing dinámico 1%
│   ├── risk_engine.py          # Kill-switch (5% día, 30% mes, 5 losses), max concurrent 2, max daily 5
│   ├── backtest_runner.py      # Orquesta todo, walk-forward, métricas
│   └── results/
│       ├── equity_curve.png
│       ├── trades.csv
│       └── metrics.json        # PF, DD, Sharpe, win%, expectancy, etc.
├── specs/
│   └── SMC_RULES.md            # Reglas ejecutables (derivadas de ESPECIFICACION_SMC.md)
├── tests/
│   ├── test_session_levels.py
│   ├── test_structure.py
│   ├── test_setup_trigger.py
│   ├── test_rejection_filters.py   # NUEVO: tests unitarios 3 condiciones §4.4
│   └── test_risk_rules.py
└── config/
    ├── risk.yaml               # Parámetros riesgo (actualizado abajo)
    ├── sessions.yaml           # Horarios sesiones México (UTC-6/UTC-5 DST)
    └── instruments.yaml        # Valor pip, contract size, spread típico por símbolo
```

**Métricas de éxito Fase 1**:
- [ ] Backtest 2+ años sin look-ahead bias
- [ ] Reglas replican ≥80% setups marcados en capturas Mariely (casos de prueba)
- [ ] Risk engine bloquea 100% violaciones en simulación
- [ ] **Tests unitarios pasan**: 3 condiciones rechazo (§4.4), double-cross, sizing 1%
- [ ] Métricas: PF > 1.3, Max DD < 15%, Sharpe > 1.0 (umbrales term sheet)

---

### Fase 2: MT5 Executor + Demo (2-3 semanas)

- `executor/mt5_bridge.py` — wrapper MT5 (o MetaApi si broker lo requiere)
- `executor/order_manager.py` — market orders (NO limit), SL/TP, modificación, cierre
- `executor/account_monitor.py` — equity, margin, posiciones abiertas
- Integración con `risk_engine` (validación pre-ejecución **inquebrantable**)
- Test exhaustivo en **cuenta demo** (mínimo 100 operaciones simuladas)

---

### Fase 3: Risk Engine Hardening (1-2 semanas)

- Librería independiente `risk_engine/` (usable por backtester + executor + futuro multi-cuenta)
- Stress tests: conexión caída, gap apertura, slippage extremo, noticias flash
- Circuit breakers: latency, spread, freeze level
- Auditoría: logging inmutable de cada decisión risk (allow/block + reason)

---

### Fase 4: Capa Avanzada (Solo si Fases 1-3 ✅)

- `volume_profile/` — TPO, VWAP, value areas, POC por sesión
- `order_flow/` — Delta, cumulative delta, footprint (requiere datos tick/L2)
- `ml_layer/` — Redes neuronales para: clasificación régimen, scoring setup, detección anomalías
- **Datos requeridos**: Tick data / Level 2 / Volume profile (costoso — evaluar ROI)

---

## CONFIGURACIÓN ACTUALIZADA (`config/risk.yaml`)

```yaml
# Verificado contra ESPECIFICACION_SMC.md (completa)
lot_sizing:
  mode: "pct_risk"           # 1% riesgo por operación (dinámico)
  risk_pct_per_trade: 0.01   # 1%
  # fixed_lot_per_1k: 0.01   # DESCARTADA

risk_reward:
  ratio: 2.0                 # 1:2 fijo (TP = 2 × SL)

breakeven:
  enabled: true
  trigger_pct_of_tp: 0.40    # 40% del camino al TP (confirmado)

partials:
  enabled: true
  stages:
    - at_pct_of_tp: 0.40     # En breakeven (40%)
      close_fraction: 0.33   # Cierra ~1/3 del lote (ej. 0.03 → cierra 0.01)

limits:
  max_concurrent_trades: 2
  max_daily_trades: 5
  daily_loss_limit_pct: 0.05
  monthly_loss_limit_pct: 0.30
  max_consecutive_losses: 5
  reactivation: "manual_only"
  scope: "per_account"       # Por cuenta individual (confirmado)

session_filters:
  avoid_friday_afternoon: true
  avoid_weekends: true
  avoid_high_impact_usd_news: true

# Nuevos parámetros de validación rechazo (§4.4)
rejection_validation:
  atr_period: 14
  max_penetration_atr: 1.0       # Perforación ≤ 1 ATR(14)
  min_wick_ratio: 0.50           # Mecha inferior ≥ 50% rango vela
  max_candles_to_reclaim: 3      # Reclaim cuerpo arriba nivel en ≤ 3 velas (ideal 1-2)
  require_volume_spike: true     # Pico tick volume en vela falso rompimiento

entry_trigger:
  type: "market"                 # Orden market, NO limit
  double_cross_required: true    # Barrido abajo → cruce arriba = entrada
```

---

## PRÓXIMAS ACCIONES INMEDIATAS (Esta semana)

| Acción | Responsable | Deadline | Estado |
|---|---|---|---|
| Enviar cuestionario broker (3 preguntas) a Vantage + VT | Usuario | Hoy | ⬜ Pendiente |
| Redactar term sheet borrador | Usuario | 2 días | ⬜ Pendiente |
| Definir fuente datos históricos + descargar muestra | Usuario | 3 días | ⬜ Pendiente |
| **Escribir `specs/SMC_RULES.md`** (reglas ejecutables) | **Agente (próximo paso)** | **Inmediato** | 🟡 Listo para empezar |
| Crear `config/sessions.yaml` con horarios México | Agente | Junto con SMC_RULES | 🟡 Listo |

---

## CRITERIOS DE "LISTO PARA FASE 1" — **SOLO FALTAN EXTERNOS**

- [x] **10 preguntas Mariely respondidas** → `ESPECIFICACION_SMC.md` completa
- [ ] 3 preguntas broker respondidas por escrito
- [ ] Term sheet firmado
- [ ] Datos históricos descargados y validados (formato, gaps, zona horaria México)
- [x] `config/sessions.yaml` con horarios exactos confirmados (por escribir)
- [x] `specs/SMC_RULES.md` reglas ejecutables (por escribir)

---

**Nota**: Este plan es intencionalmente conservador. Cada fase tiene criterio de salida objetivo. No se avanza hasta que el criterio se cumple. El risk engine (Fase 3) es el único componente que **nunca** se desactiva — está en el path crítico de cada operación desde Fase 2 en adelante.

---

**Fin de PLAN_EJECUCION.md**