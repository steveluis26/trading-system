# Trading System — sistema nuevo desde cero

Sistema de trading algorítmico con validación estadística.
**Estado: Fase 1 — scaffold listo, esperando la especificación de estrategia.**

## Correr el smoke test (verifica que el pipeline completo funciona)
```bash
python3 run_backtest.py
```
Usa datos sintéticos y una estrategia de ejemplo (cruce de medias).
Debe dar resultado **negativo**: un cruce de medias sobre random walk pierde
exactamente el costo de transacción. Si diera positivo, el backtester tendría un bug.

## Arquitectura — separación de responsabilidades desde el día uno

```
core/types.py        Bar, Signal, RiskDecision, Position
                     Research y produccion usan LOS MISMOS tipos.

strategies/          Solo producen Signal. No conocen broker, no calculan
                     lotaje, no deciden si se ejecuta.
  base.py            contrato abstracto
  template.py        plantilla mapeada 1:1 a la especificacion
  example_ma.py      ejemplo desechable (borrar al llegar la real)

risk/engine.py       VETO absoluto. Determinista, auditable, cada rechazo
                     loggeado con motivo. Limites en config/risk.yaml.

backtest/
  engine.py          event-driven, SL/TP intrabar PESIMISTA, costos reales
  walkforward.py     ventanas deslizantes (unica validacion honesta)

features/            (Fase 2) modulo UNICO compartido research<->produccion
measurement/metrics.py  Sharpe, Sortino, DD, PF, expectancy + veredicto go/no-go
execution/           (Fase 4) interfaz Broker; MetaApi entra como subclase
```

## Decisiones de diseño ya tomadas

| Decisión | Razón |
|---|---|
| Sin `vectorbt` / `backtesting.py` | Vectorizados no resuelven SL/TP intrabar (con OHLC no sabes qué tocó primero), ni filtros con estado (anti-hedging), ni lotaje dinámico. Regalan ganancias inexistentes. |
| SL antes que TP si la vela toca ambos | Pesimista por diseño. Al revés inflas el backtest. |
| Spread + slippage siempre EN CONTRA | Sin costos reales el backtest es ficción. |
| La estrategia recibe solo `bars[:i+1]` | Anti-leakage estructural: es imposible ver el futuro. |
| Walk-forward, nunca `train_test_split` | K-fold aleatorio filtra información futura en series temporales. |
| LLM fuera del loop de decisión | No determinista, no backtesteable, no auditable. Va en explicabilidad/reportes. |
| TradingView nunca en el path de ejecución | Webhooks sin entrega garantizada + train/serve skew. |
| Interfaz `Broker` abstracta | Cambiar MetaApi ↔ terminal MT5 nativo = una subclase, sin tocar estrategia ni risk. |

## Roadmap
- **Fase 1 (aquí)** — backtester + risk engine + métricas. Pregunta: ¿la estrategia
  tiene edge después de costos, **sin ML**? Go/no-go del proyecto entero.
- **Fase 2** — datos reales, feature store, triple-barrier labeling.
- **Fase 3** — meta-labeling: LightGBM predice P(TP antes que SL) sobre las señales.
- **Fase 4** — event store, ejecución MetaApi, multi-tenant, dashboard, Telegram.

## Siguiente paso
`docs/QUE_NECESITO_DE_ELLA.md` — los 3 bloqueantes.
