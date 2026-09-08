# ARCHITECTURE — Plataforma de Trading Multi-Conector (Objetivo)

> **Visión congelada:** No estás haciendo "un bot". Estás construyendo **Trading Platform / Algorithmic Trading System** con estrategia + ML, backtesting, portfolio, risk, ejecución intercambiable, TradingView, multiusuario, dashboard, Telegram, persistencia y adaptadores. **No implementar todo ahora** — la arquitectura no debe impedir ninguna capacidad después.

```
                         TRADING SYSTEM
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
         MARKET DATA       STRATEGY/AI      PORTFOLIO
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                         RISK ENGINE
                               │
                               ▼
                       EXECUTION ENGINE
                               │
       ┌───────────────┬──────┼──────────────┬──────────────┐
       ▼               ▼      ▼              ▼              ▼
     MQL5           MetaApi  Python       TradingView    futuros
       │               │      │              │
       └───────────────┴──────┴──────────────┴──────────────┘
                               │
                               ▼
                         EVENT BUS (durable, replay, orden, idempotencia)
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
         Database          Dashboard          Telegram
        Event Store      por usuario       notificaciones
        Read Model       + Telegram         por evento
        PostgreSQL       + histórico
```

## Adaptadores intercambiables (no casar con tecnología)

```
MarketDataProvider (IF)
├── DukascopyCSVAdapter
├── MT5LiveAdapter
└── SyntheticAdapter

SignalProvider (IF) — TradingView es fuente externa de eventos/alertas, no solo señal
├── InternalStrategyAdapter (SMCMultiTF/WyckoffV2 via Strategy IF)
└── TradingViewWebhookAdapter (HMAC, idempotencia, validación)

ExecutionProvider (IF)
├── MQL5TerminalAdapter
├── MetaApiCloudAdapter
└── PaperSimulatorAdapter

NotificationProvider (IF) → TelegramAdapter (y futuro email/WhatsApp/push)
VisualizationProvider (IF) → DashboardAPIAdapter → Next.js (consume Event Bus + Read Model)
```

## Dominio vs Eventos vs Estado

```
                 DOMAIN
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     Strategy     Risk      Portfolio
        │          │          │
        └──────────┼──────────┘
                   ▼
                 EVENTS (cuentan qué ocurrió, no qué es cierto)
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     Database   Dashboard   Telegram
```
- **EVENTOS TRADING:** `SignalGenerated, RiskApproved/Rejected, OrderIntent/Submitted/Filled/Rejected, PositionOpened/Modified/Closed, SL/TPTriggered, TradeCompleted, ModelPrediction/Feedback, TelegramNotificationSent`
- **ESTADO / READ MODEL:** `equity, balance, positions, drawdown, open orders, account status, strategy status` → dashboard consulta estado aunque no haya evento reciente
- **MÉTRICAS MERCADO:** `PanelSnapshot, VSA, liquidity` → `features/realtime_panel.py` (Caso A)

## Multiusuario / Multicuenta

```
USER
 ├── Trading Account A → MT5 / MetaApi
 ├── Trading Account B → MT5 / MQL5
 └── TradingView
```
Todo evento lleva `user_id, account_id, symbol, correlation_id`. `RiskEngine` scope `per_account` (`risk.yaml:40 scope per_account`). `Portfolio` aísla `equity/positions` por `account_id`.

## Misma estrategia, múltiples escenarios

```
                    SMCMultiTF
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Backtest        Paper          Live
          │              │              │
     Simulator       Simulator      Execution
                                     │
                       ┌─────────────┼─────────────┐
                       ▼             ▼             ▼
                      MQL5         MetaApi       Python
```
`SMC → Signal → Risk → OrderIntent → ExecutionProvider` (la estrategia no sabe quién ejecutó).

## CURRENT vs TARGET

**CURRENT (hoy):**
```
MarketData (CSV) → Strategy (SMCMultiTF/Wyckoff) → Risk (veto) → Backtest (simulator)
                                                              → Dashboard (acoplado, importa strategies/risk directo)
```
`core/types` inmutables, `backtest/multitf` pesimista, `measurement/metrics` — sin Portfolio, sin Event Bus, sin ExecutionProvider, sin multiusuario real.

**TARGET (objetivo):**
```
MarketData → Strategy → Portfolio → Risk → ExecutionProvider → Event Bus → Database/Dashboard/Telegram
```
Con `MQL5/MetaApi/Python` intercambiables, `TradingViewWebhookAdapter`, `Portfolio` por `account_id`, `Event Bus` durable, `PostgreSQL`.

**Estado actual (2026-09-03):**
- **Fase 1 ✓** — backtester honesto + risk + métricas
- **Fase 2-4 ↻** — MarketData live, Portfolio, Event Bus durable, Execution MQL5/MetaApi, Telegram, PostgreSQL → **reservados, no implementados**
- **Integrations esqueleto:** `docs/INTEGRATIONS/*.md` con `MetaApi rate limit, MQL5 ZeroMQ, TradingView webhook sin garantía` (`README:48`)

## Memoria
- `PROJECT_STATE.md` → foto actual, apunta a `ESTADO_REAL_ESTRATEGIAS.md`
- `DECISIONS/` → ADRs (ej. fuente única pip)
- `ERRORS/` → `KNOWN_ISSUES` / `LESSONS_LEARNED` (ej. pip 1.0 vs 100, ATR a medias)
- `EVENTS.md` → contrato con `user_id/account_id/correlation_id`
