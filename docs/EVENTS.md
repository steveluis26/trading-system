# EVENTS — TARGET DESIGN — NOT IMPLEMENTED (contrato, no API existente)

> **TARGET DESIGN — NOT IMPLEMENTED** — Event Bus requisitos: **pub/sub durable, replay, orden, idempotencia** — tecnología **no decidida** (InMemory para backtest, Redis Streams/RabbitMQ/Kafka para live se evaluará después). No decidir ahora.

## Catálogo

| Evento | Cuándo | Payload mínimo |
|---|---|---|
| `SignalGenerated` | Strategy emite `Signal` | `user_id, account_id, symbol, side, entry, sl, tp, strategy, correlation_id, context {fib, FVG, acc}` |
| `RiskApproved` / `RiskRejected` | `RiskEngine` valida | `correlation_id, approved, reason, volume` |
| `OrderIntent` | Se crea intención de orden | `correlation_id, symbol, side, entry, sl, tp, volume` |
| `OrderSubmitted` | Enviado a `ExecutionProvider` | `order_id, provider MQL5/MetaApi/Python` |
| `OrderFilled` / `OrderRejected` | Broker responde | `fill_price, commission, slippage` |
| `PositionOpened` | Orden fill → posición | `position_id, open_price, volume` |
| `PositionModified` | `BreakevenHit` / `PartialClosed` | `new_sl, close_fraction` |
| `PositionClosed` | `SL/TP/manual/kill_switch` | `close_price, pnl, close_reason` |
| `TradeCompleted` | `PositionClosed` final | `pnl_neto, duration, strategy, account_id` |
| `ModelPrediction` / `ModelFeedback` | `LightGBM` Fase 3 | `features, p_tp, outcome` |
| `TelegramNotificationSent` | Notificación enviada | `chat_id, message, correlation_id` |

Todos llevan `user_id, account_id, symbol, correlation_id, timestamp`.

## Flujo

```
SignalGenerated
      │
      ├── RiskApproved → OrderIntent → OrderSubmitted → OrderFilled → PositionOpened → ... → PositionClosed → TradeCompleted
      │         │              │              │              │                         │
      │         └── RiskRejected → Telegram 🛑 "exposición máxima"
      │
      ├── Database (Event Store append-only)
      ├── Dashboard (Read Model por usuario: equity, positions, drawdown)
      └── Telegram (NotificationProvider)
```

Ejemplo Telegram `OrderFilled`:
```
🟢 EURUSD BUY
Entrada: 1.16842 SL: 1.16692 TP: 1.17142 Riesgo: 1% Estrategia: SMC V4 Cuenta: ****1234
```

## Trazabilidad para aprendizaje

```
señal → contexto → features → predicción → decisión → ejecución → resultado → feedback → modelo
```
Conservar `Signal.context` + `Position` + `TradeCompleted` en `PostgreSQL` (`trades, trade_features, backtest_runs`) para futuro `meta-labeling`.

## Actual vs Objetivo

| Concepto | Actual | Objetivo |
|---|---|---|
| `Signal` | ✅ `core/types.py:26` existe | conservar |
| `RiskDecision` | ✅ existe | conservar/evolucionar a `RiskApproved/Rejected` |
| `Position` | ✅ existe | evolucionar (añadir `user_id/account_id`) |
| `SignalGenerated` | ❌ futuro | `Strategy` emite |
| `RiskApproved/Rejected` | ❌ futuro | `RiskEngine` valida |
| `OrderIntent/Submitted/Filled/Rejected` | ❌ futuro | `ExecutionProvider` |
| `PositionOpened/Modified/Closed` | ❌ futuro | `Execution` |
| `TradeCompleted` | ❌ futuro | `PositionClosed` final |
| `ModelPrediction/Feedback` | ❌ futuro | `LightGBM` Fase 3 |
| `Event Bus` | ❌ futuro | `InMemory` backtest, durable para live |

## Estado hoy
- `core/types.py` tiene `Signal/RiskDecision/Position` (no `Order` aún) — `execution/__init__.py` vacío
- `features/realtime_panel.py` es `VisualizationProvider` aislado (Caso A)
- `dashboard/backend.py` es orquestador acoplado (importa `strategies`/`risk` directo) — debe pasar a `api/readmodel.py` + `adapters/dashboard_subscriber.py` que consuman `Event Bus`
