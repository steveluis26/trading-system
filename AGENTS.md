<!-- BEGIN:trading-system-agent-rules -->
# Trading System — Reglas para agentes (OpenCode, Claude, Codex, Cursor, etc.)

Este NO es un bot MT5 con una sola conexión. Es una **plataforma de trading multi-conector** con arquitectura de adaptadores.

## Autoridad
- `docs/ESPECIFICACION_SMC.md` → **AUTORIDAD SOBRE LA ESTRATEGIA** (qué debe hacer)
- `docs/ESTADO_REAL_ESTRATEGIAS.md` → **AUTORIDAD SOBRE EL ESTADO AUDITADO** (qué está implementado realmente, con grep VETO/PESO)
- Conflicto `SPEC ≠ CODE` → `CODE NO SE ASUME CORRECTO` → registrar discrepancia → decisión humana → actualizar SPEC/DECISIÓN → modificar código
- `docs/PROJECT_STATE.md` es índice/puerta de entrada, apunta a `ESTADO_REAL`, no lo reemplaza aún

## Arquitectura agnóstica (no elegir tecnología todavía)
- `MarketDataProvider` → DukascopyCSV / MT5 Live / Synthetic
- `SignalProvider` → Internal Strategy (SMCMultiTF/Wyckoff) + **TradingView como fuente externa de eventos/alertas** (webhook con validación/idempotencia, no solo señal)
- `Strategy/AI` → `Portfolio (por user_id/account_id)` → `Risk Engine` → `Execution Engine` → `Event Bus`
- `ExecutionProvider` → `MQL5` / `MetaApi` / `Python` (intercambiables, ninguno decidido)
- `NotificationProvider` → `Telegram` (y futuro email/WhatsApp/push) — consumidores de eventos, no `if trade: telegram.send()` en el motor
- `VisualizationProvider` → `Dashboard` por usuario (USER→Account→MT5/MetaApi+TradingView) — consumidor de `Event Bus` y `Read Model`, no orquestador
- `Event Bus` requisitos: pub/sub durable, replay, orden, idempotencia — tecnología **no decidida** (InMemory para backtest, Redis Streams/RabbitMQ/Kafka para live se evaluará después)
- `Database` / `Event Store` + `Read Model` + `PostgreSQL` para trades/features/backtest_runs/model_feedback — **reservado conceptualmente, no implementado** (Fase 3+)

## Memoria en Git, no en sesión
- `docs/ARCHITECTURE.md` → arquitectura objetivo
- `docs/EVENTS.md` → contrato de eventos con `user_id/account_id/correlation_id`
- `docs/PROJECT_STATE.md` → foto actual (Fase, estrategia, instrumentos, último backtest, próximo objetivo)
- `docs/DECISIONS/` → ADRs (ej. ADR-001 fuente única pip)
- `docs/ERRORS/` → `KNOWN_ISSUES.md` / `LESSONS_LEARNED.md`
- `docs/INTEGRATIONS/{MQL5,MetaApi,Python,TradingView,Telegram}.md` → esqueleto
- `docs/ROADMAP.md` → Fases 1-4

**Después de cada trabajo importante, el agente debe:** modificar código → ejecutar tests → validar → **actualizar `PROJECT_STATE.md` y `DECISIONS.md`** — la memoria vive en Git, no en `opencode.db`.

## Reglas críticas (obligatorias)
1. **Ningún agente puede modificar una regla de estrategia, risk, sizing, sesiones, ATR, volumen, SL/TP o ejecución para hacer pasar un test/backtest.** Si hay discrepancia `spec↔código↔test↔resultado`, registrarla como conflicto y solicitar decisión humana.
2. **Sizing/pip/ATR/sesiones/volumen/SL/TP quedan congelados** hasta que se tenga la captura VT Markets (contract size, tick size, tick value) — no tocar para "que no dé 0 trades" o "para que cuadre el número".
3. **Wyckoff → PENDING**, sin intentar corregirlo ni integrarlo, hasta que v4 tenga lectura limpia con sizing correcto. No mezclar fixes de sizing con vetos de volumen/sesiones en la misma corrida.
4. **No decidir tecnología prematura:** `Redis/Kafka` para Event Bus, `PostgreSQL` para aprendizaje, `MQL5 vs MetaApi vs Python` — documentar requisito, no elegir.
5. **Candado pip:** `grep -rn "pip_size\|pip_value" config/instruments.yaml risk/config.py` debe quedar como verificación en `PROJECT_STATE.md` — localizar todas las referencias a `1.0`, `100`, etc., marcar discrepancia como `UNRESOLVED` hasta contrastar con captura VT, no modificar código.

## Cómo validar cambios
- `RiskConfig` lee `pip_value_per_microlot` vs `pip_value_usd_per_standard_lot` — verificar con `grep` antes de tocar
- `sizing 1%` → `SL45 XAU 0.02 / $90 0.90%` y `GBP SL22 0.45 / $99` deben dar ~1% (test lee de `instruments.yaml`, no hardcode)
- `evolución ALL` con `initial 30k` (no 10k), `PeriodTable >0/<0` con `planos`
- `Wyckoff Lab` sliders deben disparar `fetch` con `lab_params` y cambiar `zones`/`candles` (no placebo)

## Estructura de carpetas (objetivo, no implementar todo ahora)
```
docs/
├── PROJECT_STATE.md
├── ARCHITECTURE.md
├── EVENTS.md
├── STRATEGY/{V4.md,RULES.md,RISK.md}
├── INTEGRATIONS/{MQL5,MetaApi,Python,TradingView,Telegram}.md
├── DECISIONS/ADR-*.md
├── ERRORS/{KNOWN_ISSUES.md,LESSONS_LEARNED.md}
└── ROADMAP.md
```

## Stack
Next.js 14 + FastAPI + Pydantic + `core/types` inmutables (`Bar/Signal/RiskDecision`) — leer `node_modules/next/dist/docs/` antes de tocar frontend.

<!-- END:trading-system-agent-rules -->
