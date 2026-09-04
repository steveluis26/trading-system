# ESTADO REAL DE ESTRATEGIAS — Fuente de verdad 2026-09-03

> **Objetivo:** Qué confirmó tu socia vs qué ejecuta hoy el código vs qué es peso/placeholder. Evidencia con `grep` literal (archivo:línea). Separa del spec original (qué debería hacer) — este es qué hace hoy.

**Fuentes:** `docs/ESPECIFICACION_SMC.md` (COMPLETA 24-26ago, 16p) · `docs/ESTRATEGIA_EXTRAIDA.md` (encuesta + 7 aclaraciones F1-F8) · `docs/AUDITORIA_WYCKOFF_VS_SPEC.md` (9 capturas + 3 respuestas ventana 15m / SL+pausar / US+otros bancos) · `strategies/smc_multitf.py` (293L) · `strategies/wyckoff_v2.py` (265L) · `config/wyckoff.yaml` (46L) · `config/risk.yaml` (131L) · `risk/config.py` · `dashboard/backend.py` (849L) · `measurement/metrics.py`

**Leyenda:** `VETO` = `return None` bloquea y afecta métricas · `PESO` = calcula pero solo en `context` · `DESCONECTADO` = YAML definido nunca leído · `PARCIAL` = 1-2/3 condiciones

---

## 1. SMC — Mariely

| # | Concepto | Confirmado por socia | Implementado real | Estado |
|---|---|---|---|---|
| 1.1 | **Universo** | EURUSD/GBPUSD/XAUUSD, D1 macro, 4H/1H impulso, 15M zona, 5M BOS, max2 abiertas, 5/día, rotación par distinto (`ESPECIFICACION_SMC.md:12`) | `smc_multitf.py:126-132` requiere `len(D1/H1/M15)>=30`, `risk/config.py:16` max2/1/5, rotación **no codificada** | Placeholder |
| 1.2 | **Sesiones/TZ** | Asia 18-03, London 02-11, NY 07-16 México `America/Mexico_City` UTC-6/-5 DST (`ESPECIFICACION_SMC.md:13`, `sessions.yaml`) | `smc_multitf.py:62-80` `_session_of_mx` 0-7 asia, 7-11 london, 11-15 ny_open (≠ spec 02/11) · `sessions.yaml` correcto pero **SMC no lo usa** | DESCONECTADO |
| 1.3 | **Tendencia D1** | HH/HL pivotes sesión, no velas | `smc_multitf.py:175-204` pivotes `L=3,R=3` `high==max(wh)` — conteo velas | PARCIAL |
| 1.4 | **Impulso H1** | Solo a favor D1 | `smc_multitf.py:150-163` EMA50 H1 `if BUY and close<EMA50: return None` | VETO (propuesta no confirmada) |
| 1.5 | **Confluencia** | 2-3 sesiones mismo nivel → peso 1.5 | `smc_multitf.py:166` `level=ref[low]` peso implícito | PESO |
| 1.6 | **Double Cross** | Rompe→cierre arriba→cruza arriba market | `smc_multitf.py:240-252` 1 vela `swept && closed_right` misma vela, `_sweep_state` nunca usado | PARCIAL |
| 1.7 | **Filtros 3** | depth≤1ATR, mecha≥50%, reclaim≤2 | `smc_multitf.py:233` `// ATR removido por petición socia` (solo referencia), `wick 50%` VETO (249/276), `reclaim 1 vela` | PARCIAL |
| 1.8 | **Volumen** | Pico tick vol 1.5 | `grep volume smc_multitf.py` 0 líneas; Wyckoff `wyckoff_v2.py:133-149` solo peso | PESO |
| 1.9 | **SL/TP** | SL=TP/2 RR2.0 | `smc_multitf.py:254 sl=level-atr*0.5` `tp=entry+dist*2.0` | PARCIAL |
| 1.10 | **BE 40%** | SL→BE 40% + 1/3 parcial | Strategy no toca BE, `backtest/multitf.py:138` `prog>=40%` + `RiskConfig be 40` | VETO real |
| 1.11 | **Sizing** | 1% dinámico confirmado (0.022 lotes a SL45 XAU = $100) vs lotes fijos 0.10 = 4.5% (XAU) / 0.045% (con bug 1.0) | `config/instruments.yaml:8 XAU 1.0 per 0.01 lot` → `risk/config.py:100` `usd_per_pip()` importa (fuente única), `backtest/multitf.py:222` **mantiene fijo** `vol=0.01*equity/1000` (0.10 a 10k) porque 1% con SL XAU 1700 pips daría 17% riesgo real con vol 0.01 min — test `test_sizing_1pct` documenta ambos | **FIX pip 2026-09-03: fuente única, sizing sigue fijo 0.10 (4.5% XAU) hasta SL más corto** |
| 1.12 | **Kill-switch** | 5%/30%/5 manual | `risk/config.py:16` + `multitf _risk_check 190` | VETO real |
| 1.13 | **Filtros duros** | No noticias USD, no finde | Horario VETO, noticias sin calendario | PARCIAL |

---

## 2. Wyckoff

| # | Spec | Implementado real | Estado |
|---|---|---|---|
| 2.1 | **Volumen Effort/Result** solo armonía → MARKUP | `_volume_harmony 133-149` calcula pero `184-196` `// no vetar, solo peso` | PESO |
| 2.2 | **TP fib 1.272/1.618** | `tp1=lo+1.272*diff` calculado pero `tp=tp_rr entry+2*R` para pasar `rr[2.0]` — `tp_fib` solo `context` | PESO |
| 2.3 | **BE pct_40\|fib_1272** | `wyckoff.yaml be_mode pct_40`, `wyckoff_v2 45,89` lee YAML, `backend 62` `pct_40→40 fib_1272→100` | CONFLICTO |
| 2.4 | **Sesiones UTC** `london[02,11] ny[07,16] asia[18,03]` | `SESSIONS_UTC 57` + `_in_wyckoff_session 105` pero veto comentado `157` | DESCONECTADO |
| 2.5 | **FVG OR peso** | `any(618-786)` peso | OK |
| 2.6 | **Filtros** depth≤1ATR | `MAX_DEPTH 1.0` nunca `if depth>` | DESCONECTADO |
| 2.7 | **Acumulación ≤1ATR 20 velas** | `rh-rl<=1.5*atr` `193` pero `if not acc_ok` comentado | PESO |
| 2.8 | **Invalidación <swing_low** | `if close<lo return None` parcial | PARCIAL |
| 2.9 | **8 pendientes** | Solo `sessions_utc` cableado | 7/8 DESCONECTADO |

---

## 3. Config definido vs usado

| Param | Definido | Lee código | Usado donde | Estado |
|---|---|---|---|---|
| `wyckoff be_mode pct_40` | Sí | `wyckoff_v2 89` | `backend 62` | OK |
| `wyckoff ATR 1.5 / GAP 0.2` | Sí | `wyckoff_v2 71,76` | `193` `211` | PESO |
| `wyckoff pending sessions_utc` | Sí | `wyckoff_v2 94` | `_in_wyckoff` comentado | DESCONECTADO |
| `risk rr 2.0 / BE 40` | Sí | `risk/config.py 81` | `multitf _risk_check` | VETO |

---

## 4. Backend `strategy` param

`GET /api/backtest/{symbol}?strategy=v4|wyckoff` → `_get_strategy` + `_get_risk_for_strategy` (Wyckoff `rr [0.4,3.0]` para fib), cache `bt_{prefix}_*`

---

## 5. Métricas

`win_rate = wins>0 / n`, `pnl_by_window` con `initial 30k ALL` (corregido), `veredicto` umbrales `100 trades / 250 días / Sharpe 1 / DD15 / PF1.2`, `PeriodTable >0/<0` con `planos`

---

## 6. Origen por estrategia — de dónde toma cada valor

| Estrategia | Parámetro | Fuente real (archivo:línea) | Valor usado hoy |
|---|---|---|---|
| **v4 SMC** | `pip_size, usd_per_pip` | `config/instruments.yaml:8 XAU 1.0 per 0.01 lot` → `risk/config.py:100` `usd_per_pip()` (fuente única) | XAU 0.01 / $1 (0.10=$10), EUR 0.0001 / $10 |
|  | `Sizing` | `backtest/multitf.py:222` `vol=0.01*equity/1000` fijo | 0.10 lotes a 10k (4.5% XAU 45pips, 0.045% con bug previo) |
|  | `SL/TP RR` | `strategies/smc_multitf.py:92 RR2.0` + `254 sl=level-atr*0.5` | RR 2.0 fijo |
|  | `Filtros mecha` | `smc_multitf.py:249 wick>=50%` | VETO |
|  | `Sesiones` | `sessions.yaml` pero `smc_multitf.py:62` `_session_of_mx` hardcode | DESCONECTADO |
| **Wyckoff v2** | `pip` | `config/instruments.yaml:8 XAU 1.0` → `risk/config.py` (misma) | XAU $1 per 0.01 |
|  | `Sizing` | `backtest/multitf.py:222` fijo igual que v4 | 0.10 lotes |
|  | `FIB 0.618/0.786` | `config/wyckoff.yaml:24-25` → `wyckoff_v2.py:84` `FIB_ENTRY` | 0.618/0.786 |
|  | `FIB 0.618/0.786` | `config/wyckoff.yaml:24-25` → `wyckoff_v2.py:84` `FIB_ENTRY` | 0.618/0.786 |
|  | `TP` | `wyckoff_v2.py:231 tp_fib` en `context` pero `tp=tp_rr` real | RR 2.0 (fib ref) |
|  | `ATR acc` | `config/wyckoff.yaml:9 atr_mult 1.5` → `wyckoff_v2.py:71,193` `rh-rl<=1.5*atr` | PESO |
|  | `Sesiones UTC` | `config/wyckoff.yaml:39 pending.sessions_utc` → `wyckoff_v2.py:94` leído pero veto comentado `157` | DESCONECTADO |
|  | `BE_MODE` | `config/wyckoff.yaml:6 be_mode` → `wyckoff_v2.py:89` + `backend 62` `pct_40→40` | pct_40 |
| **Ambas** | `Risk BE 40%` | `config/risk.yaml:20-23` → `risk/config.py:79` → `backtest/multitf.py:138` | 40% |
|  | `Kill-switch 5%/30%/5` | `config/risk.yaml:34` → `risk/config.py:16` → `multitf _risk_check` | VETO |

**Causa raíz duplicado pip:** `instruments.yaml:65 XAU 100.0` (correcto, 0.01=$1) vs `risk/config.py:46 XAU 1.0` (bug 100×) — ahora `risk/config.py` importa de `instruments.yaml` como fuente única, test `test_pip_source_is_instruments` lo garantiza.

## Anexo — Greps literales

```bash
grep -n "MAX_DEPTH_ATR|MIN_WICK" smc_multitf.py # 88-90 def, 249/276 wick VETO, depth no veto
grep -n "return None" wyckoff_v2.py # 154,160,167,179,210,227,230,241,256,259 — 4 comentados peso
grep -n "vol_ok|tp_fib|sessions_utc" wyckoff_v2.py # 185 vol_ok peso, 231 tp_fib context, 57 SESSIONS_UTC desconectado
grep -n "usd_per_pip.*XAU" risk/config.py config/instruments.yaml # risk 46 XAU 1.0→100.0 fix, instruments 65 100.0 fuente única
```
