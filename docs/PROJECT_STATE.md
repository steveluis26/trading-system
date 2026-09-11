# PROJECT STATE — Foto actual (índice, no reemplaza a ESTADO_REAL)

> **Autoridad:** `ESPECIFICACION_SMC.md` → qué debe hacer · `ESTADO_REAL_ESTRATEGIAS.md` → qué está implementado realmente (con grep). `PROJECT_STATE.md` es índice/puerta de entrada.

## Estado actual
- **Fase:** `Fase 1 ✓` (backtester honesto + risk + métricas) · `Fase 2-4 ↻` (MarketData live, Portfolio, Event Bus, Execution MQL5/MetaApi, Telegram, PostgreSQL reservados)
- **Estrategia:** `v4 SMC` (activa en demo `44tr PF0.39` con 1% dinámico) y `v2 Wyckoff` (`PENDING`, 12tr, sin volumen/TP fib real)
- **Sizing — 2 stacks, no 1% único:**
  - `Stack legacy / dashboard` `backtest/multitf.py:222` → `1% dinámico` `vol=(equity*0.01)/(SL*upp)` con veto `vol<0.01` (XAU SL45 0.02 / $90 0.90%, GBP SL22 0.45 / $99) — **activo**
  - `Stack nuevo` `backtester/config_loader.py` + `backtester/position_simulator.py` → `lots_per_1000: 0.01` (fijo, `risk.yaml:8 mode: fixed_lot`) — **aún declara fijo, no 1%**
  - `Config` `config/risk.yaml:5` sigue `mode: fixed_lot` — no es 1% canónico global aún. Por eso `PROJECT_STATE` no puede decir `1% único`.
  - **CANDADO — pip_value XAU:** `pip_value_usd_per_standard_lot` para `XAUUSD` **DEBE ser 1.0**. Verificado el 2026-09-10 contra MT5 Specification de VT Markets (`Contract size=100`, `Tick size=0.01`, `Tick value=1` → `$1/pip/lote`). Cualquier cambio futuro a este valor requiere nueva evidencia de Specification (captura de MT5), no debe modificarse por asunción ni para "recuperar" un número de trades específico. Ver commit `fe5247a` para el fix aplicado.
- **Instrumentos:** `XAUUSD, EURUSD, GBPUSD` · `data/raw` 29 CSV evtradelabs 2020-2026 (`XAU 5m 449k`) · `data/cache` separado por `strategy` (`bt_v4_*`, `bt_wyckoff_*`)

## Último backtest (v4, 2 años 2024-2026, sizing 1% limpio)
- `XAU 44tr PF0.39 -1471$ win 20% DD14.7%` · `EUR 16tr PF0.02 -2557$` · `GBP 14tr PF0.006 -2844$` → `INSUFICIENTE <100` (ruido), `SIN EDGE` (PF<1.2, Sharpe<1)
- `6 años XAU` → `83tr PF0.46` aún `<100` — sigue insuficiente, no es edge

## Último cambio
- `ef6bb84` pip escala única `standard lot` (XAU 100) + `pip_value_per_microlot` renombrado, test lee de yaml, `0.02` en vivo verificado

## Candado de verificación — pip (verificado 2026-09-10, no modificar sin nueva evidencia)
```bash
grep -rn "pip_size\|pip_value" config/instruments.yaml risk/config.py
# Debe dar: instruments.yaml XAU pip_size 0.01, pip_value_usd_per_standard_lot 1.0 (MT5 Spec: Contract 100, Tick 0.01, Tick value 1 → $1/pip/lote)
# risk/config.py debe leer pip_value_usd_per_standard_lot (1.0), no pip_value_per_lot
# Si aparece 100.0 como fuente, es bug 100× (revertido en fe5247a)
```
- **Estado:** `RESUELTO` el 2026-09-10 contra MT5 Specification de VT Markets (`Contract size=100`, `Tick size=0.01`, `Tick value=1` → `$1/pip/lote`) — ver commit `fe5247a`
- **Regla:** ningún agente puede cambiar `pip_size/pip_value/sizing` sin nueva captura de Specification; cualquier cambio futuro requiere evidencia, no asunción

## Problemas conocidos (de ESTADO_REAL)
- `sizing` fijo vs 1% resuelto, pero `SL` XAU `atr*0.5` da 500 pips → `vol 0.005 <0.01` y `0tr` con `1%` si se usa `100` (por eso se mantiene `1.0` per 0.01 para demo hasta captura VT)
- `Wyckoff` 5 vetos peso (volumen, TP fib, sesiones UTC, ATR acc, etc.) — `PENDING`
- `Sesiones v4` hardcode `0-7/7-11` ≠ spec `02-11`, `Tendencia D1` por velas no sesión, `Evolución` acumulado vs delta (ya corregido a `30k` para ALL)

## Próximo objetivo
- **Hasta captura VT:** no tocar `sizing/pip/ATR/sesiones/volumen` — 4 fixes paralelos no monetarios (sesiones, D1 pivotes, evolución delta, comentario ATR) pueden avanzar
- **Después de captura:** recalibrar `pip_size` XAU con dato real y re-correr 6 años `XAU/EUR/GBP` para ver si `≥100tr`

## Decisiones pendientes
- `Wyckoff` TP fib real vs RR 2.0, `BE fib_1272` vs `pct_40`, `8 pendientes` (fvg_fresh, time_stop, etc.)
- `Event Bus` tecnología (InMemory vs Redis/Kafka) — requisito documentado, no decisión

## Archivos críticos
`strategies/smc_multitf.py`, `strategies/wyckoff_v2.py`, `backtest/multitf.py:222` (sizing), `risk/config.py:46` (pip), `config/instruments.yaml:65`, `dashboard/backend.py` (`strategy` param), `measurement/metrics.py` (veredicto)

## NO MODIFICAR SIN AUTORIZACIÓN
`sizing, pip, ATR, sesiones, volumen, SL/TP, ejecución` — si hay discrepancia `spec≠code↔test↔resultado`, registrar conflicto, no "arreglar" para que pase.

