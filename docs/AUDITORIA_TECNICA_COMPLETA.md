# AUDITORÍA TÉCNICA COMPLETA — Baseline pre-refactor

**Fecha:** 2026-09-03
**Versión auditada:** `6a8d0c1` (con `AGENTS.md` y memoria ya alineados, sin tocar código funcional)
**Método:** `grep`/`cat -n`/`git diff`/`pytest` + ejecución `backtest/multitf` con `SL45` y `SL 677` + cache `data/cache/bt_*_ALL.json`
**Regla:** `SPEC ≠ CODE` → discrepancia · `CODE ≠ TEST` → discrepancia · `TEST ≠ RESULTADO` → discrepancia · **Nadie modifica código para hacer coincidir las tres**

---

## Resumen ejecutivo

| Área | Estado | Severidad |
|---|---|---|
| **Sizing / PIP** | `PIP` fijo `0.0001` → XAU costo 85× mal + `XAU pip 1.0 vs 100` duplicado + `SL 677` con `1%` da `0.0014 → rechaza` (XAU 0tr) vs `2.22` con bug | **CRÍTICA** |
| **Backtesting** | `daily_levels` con futuro (lookahead) + 2 motores con fills/costos/sesiones distintos | **CRÍTICA** |
| **Risk** | `halted` nunca true, `consecutive_losses` reseteado diario, 3 engines duplicados | **CRÍTICA** |
| **Config** | `~9` muertos, `5` duplicados, `3` desconectados, `pip_value_per_lot` vs `standard_lot` | **CRÍTICA** |
| **Arquitectura** | `dashboard` orquestador acoplado, `execution` vacío, stacks duplicados | **CRÍTICA** |
| **Dashboard** | `P&L` duplicado 3 fórmulas, cache `30k` magic, `ALL` incompleto | **ALTA** |
| **Tests** | Bimodal: nueva gen OK, vieja gen ancla bug `1.0` | **ALTA** |

---

## 1. SIZING / PIP — 🔴 CRÍTICA

### Hallazgo
`PIP` fijo `0.0001` en `backtest/multitf.py:22` → XAU costo 85× mal.

**Evidencia:**
```python
# backtest/multitf.py:22
PIP = 0.0001
# risk/config.py:43
pip_size: {"XAUUSD": 0.01}  # correcto por símbolo
# backtest/multitf.py:115
sp = self.cfg.spread(sym) * PIP  # XAU spread 35 * 0.0001 = 0.0035 precio, pero pip XAU es 0.01 → 0.0035/0.01 = 0.35 pips reales, debería ser 0.01*35=0.35 precio (mismo número por coincidencia, pero escala confusa)
# core/types.py:65
def pnl(self, usd_per_pip=10.0, pip_size=0.0001) # default forex, XAU usa 0.01 pero si no se pasa, 0.0001 → 100×
```

**Números concretos — XAU SL 45 pips vs SL 677 pips (trade real 2024-11-27):**

| SL precio | SL pips con `pip 0.01` | SL pips con `pip 0.0001` (bug) | `vol` con `1%` (equity 10k, upp 100) | Riesgo | `vol` con `1.0` (bug) | Factor error |
|---|---|---|---|---|---:|---|
| 0.45 (45×0.01) | 45 | 4500 | `0.022 → 0.02` | `$90 0.9%` | `2.22` | 100× vol | 
| 6.77 (SL real 2645→2652) | 677 | 67700 | `0.0014 → <0.01 rechaza` | `SL muy ancho` | `0.014 → 0.01` | 100× |

- **Con `pip 0.01` correcto:** `SL 45 → 0.02` OK, `SL 677 → 0.0014` → `0tr XAU` con `1%` (rechazado, no 44tr)
- **Con `pip 0.0001` bug:** `SL 45 → 2.22` (100×), `SL 677 → 0.014` (10×) → `44tr` con `1%` pero riesgo real `100×` mayor si se usa `pip 0.0001` en `pnl` sin pasar `0.01`

**Impacto financiero:** `P&L` XAU con `PIP` fijo se calcula 100× mal si `dashboard/backend.py:788 pos.pnl()` sin args usa `pip_size 0.0001` para XAU.

**Decisión humana pendiente:** Validar `pip_size XAU` contra **VT Markets Specification** (Contract size, Tick size, Tick value) — captura de `Market Watch → Specification` con `0.01` vs `0.10`. Hasta entonces, `pip_size` queda `UNRESOLVED`.

**Separar valor de pip vs distancia/escala:** `pip_value` bug (`1.0` vs `100.0` per lote) ya corregido a `pip_value_usd_per_standard_lot 100.0` (XAU) con test que lee de `instruments.yaml`, no hardcode. `pip_size` es otro bug independiente (escala de pips, no de valor).

---

## 2. BACKTESTING — 🔴 CRÍTICA

### Lookahead `daily_levels` — Bug confirmado

**Flujo temporal:**
```
t = vela M5 evaluada (ej. 2024-09-12 14:30)
        ↓
backtester/backtest_runner.py:137 calculate_session_levels_for_backtest(start_dt, end_dt)
        ↓ usa TODO el rango (futuro) para calcular High/Low sesión
        ↓
macro_structure = analyze_structure_for_backtest(daily_levels_only, candles_4h, current_date) :161
        ↓ incluye velas posteriores a t
        ↓ SÍ puede alterar decisión (falso BOS)
```

**Evidencia:**
```python
# backtester/backtest_runner.py:137-142
daily_levels = calculate_session_levels_for_backtest(start_dt, end_dt)  # end_dt = 2026-05-15, futuro respecto a t=2024-09-12
# vs backtest/multitf.py:77-82 slice_until time<=t (correcto, sin futuro)
```

**Severidad:** `CRÍTICA` — integridad del backtest. No es riesgo, es bug.

**Diferencias entre motores:**

| Aspecto | `backtest/multitf.py` (dashboard, canónico) | `backtester/*` (walk-forward, Pydantic) |
|---|---|---|
| **Fills + costos** | `fill = entry ± spread/2 ± slippage` `115` + `commission 7` `PIP 0.0001` bug | `position_simulator:283` sin spread/slippage/commission |
| **Sesiones** | `strategies/smc_multitf:62` `0-7/7-11` hardcode | `session_calculator:65` `18-03/02-11/07-16 America/Mexico_City` DST |
| **Sizing** | `1%` `multitf:222` con `pip 0.01` | `lots_per_1000` fijo `position_simulator:43` |
| **Señales** | `smc_multitf` directo | `SetupDetector→TriggerEngine` con `ATR`/`volume` |
| **Resultado** | `n_trades`/`pnl` con costos | sin costos, P&L distinto |

**Decisión:** Elegir motor canónico (`multitf` honesto) y archivar el otro, o unificar.

---

## 3. RISK — 🔴 CRÍTICA (halted nunca true)

**Evidencia:**
```python
# backtest/multitf.py:68
halted = False; halt_reason = ""
# ... 87 day[0] = t.date(); daily_pnl[0]=0; consecutive_losses[0]=0  # resetea diario
# 193
if halted:
    return f"HALT: {halt_reason}", 0.0  # nunca entra porque halted nunca se pone True
# 196-204
if consecutive_losses >= c.max_consecutive_losses:  # 5
    return f"{consecutive_losses} perdidas consecutivas (BLOQUEO)", 0.0
# Pero consecutive_losses se resetea a 0 cada día (87), entonces 5 nunca se alcanza si las pérdidas están distribuidas
```

```python
# risk/engine.py:10 RiskLimits(max_open 3 vs risk/config 2), daily 3% vs 5%, dd 15% vs 30%
# backtester/risk_engine.py:42 validate_pre_trade con is_blocked, monthly_loss, news_filter (siempre False 36-40)
```

**Impacto:** `kill-switch 30%` y `5 consecutivas BLOQUEO` declarados en `ESPECIFICACION_SMC.md:141` nunca se activan operacionalmente.

**Decisión:** Definir `halted` con `bar.time` (no `now()`), no resetear `consecutive_losses` diario, y unificar 3 engines en uno con `per_account`.

---

## 4. CONFIGURACIÓN — CRÍTICA

| Param | Definido | Lee código | Usado | Estado |
|---|---|---|---|---|
| `pip_value_per_lot 1.0` (microlote) vs `pip_value_usd_per_standard_lot 100.0` | `instruments.yaml:8` + `65` | `risk/config 63` leía `1.0` ahora `100` | `1.0` DEPRECATED pero aún en yaml | Duplicado |
| `spread 30/1.5/2.0` | `instruments.yaml` | `risk/config spread_default 35/12/18` | Duplicado |
| `mode fixed_lot` vs `1%` | `risk.yaml:5` `fixed_lot` | `multitf` fuerza `1%` | Muerto |
| `sessions.yaml` | `02-11` etc. | `smc_multitf` hardcode `0-7` | DESCONECTADO |

**Decisión:** Fuente única `instruments.yaml` para `pip/pip_value`, borrar `pip_value_per_lot` legacy, unificar `risk.yaml` con `backtester/config_loader`.

---

## 5. ARQUITECTURA — CRÍTICA

- `dashboard/backend.py:22-29` importa `strategies`, `risk`, `backtest` directo — `VisualizationProvider` acoplado, no consumidor de `Event Bus`
- `execution/__init__.py` vacío — `MQL5/MetaApi/Python` solo docs
- `core/types` vs `backtester/models` duplicados (Bar/Signal/Position)
- `data/loader` vs `backtester/data_loader` TZ `UTC` vs `America/Mexico_City`

---

## 6. DASHBOARD, TESTS, MÉTRICAS, DATOS

- `P&L` 3 fórmulas (`core/types`, `multitf`, `position_simulator`) con `pip`/`spread` distintos
- `evolución ALL` ya corregido `30k` (antes `10k` bug `14738` → `0tr` ahora `0/20/2`)
- Tests bimodal: `test_config_loader` espera `1.0` vs `test_position_sizing` espera `100.0` — conflicto pendiente

---

## Prioridad antes del refactor

**P0 — No tocar hasta resolver/decidir (bloqueante dinero/seguridad):**
- Sizing/PIP XAU (con captura VT) — ya tenemos `1%` con `100` pero `XAU 0tr` con `SL atr*0.5` debe decidirse: ¿SL más corto o mantener veto?
- Lookahead `daily_levels` con futuro
- Risk `halted` nunca true + `consecutive_losses` reseteado diario
- Config contradictoria (`pip_value_per_lot` vs `standard_lot`)

**P1 — Resolver durante refactor arquitectónico (duplicación):**
- Engines duplicados (3 risk, 3 backtesters)
- Ejecución inexistente (`execution/` vacío, sin `Broker` IF)
- Dashboard acoplado (orquestador vs consumidor)
- Config muerta/duplicada/desconectada

**P2 — Deuda técnica:**
- Tests faltantes (risk/engine, fills, lookahead, multi-TF sync)
- Componentes huérfanos (`walkforward.py` 0 callers)
- `core/types` hardcode `usd_per_pip` defaults

**Decisiones que requieren humano (no automatizar):**
- `pip_size` XAU `0.01` vs `0.10` — validar con VT Markets Specification (captura)
- Sizing canónico: ¿`1%` dinámico único o `fixed_lot` para XAU con SL ancho?
- Motor de backtest canónico: ¿`multitf` (honesto) o `backtester` (Pydantic)?
- Política riesgo definitiva: ¿reset diario de `consecutive_losses` o `BLOQUEO` total?
- Ejecución: ¿MQL5 vs MetaApi vs Python como primer adaptador?
- Estrategia: ¿Wyckoff con `TP fib` real y `volumen veto` o mantener como peso?

---

**Siguiente paso:** Congelar este baseline y no tocar arquitectura/código hasta decidir las 6 decisiones humanas listadas.
