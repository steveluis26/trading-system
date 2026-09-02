# Especificación SMC - Estrategia de Trading (Mariely) — **COMPLETA**

**Fuente**: Cuestionario original (12 preguntas) + 7 aclaraciones videollamada + 14 capturas TradingView + 10 respuestas finales  
**Fecha**: 24-26 agosto 2026  
**Estado**: **LISTA PARA FASE 1** — Todas las ambigüedades resueltas → escribir `specs/SMC_RULES.md`

---

## 1. Universo Operativo

| Parámetro | Valor |
|---|---|
| **Instrumentos** | EURUSD, GBPUSD, XAUUSD (oro) |
| **Timeframes** | 1D = tendencia macro; 4H/1H = confirmación impulso vs retroceso; 15M = setup/identificación zona; 5M = entrada (BOS confirmado) |
| **Sesiones referencia** | Asia, Londres, Nueva York — se usa **High/Low de cada sesión** (horarios fijos), no indicadores |
| **Días/horarios excluidos** | Viernes tarde, fines de semana, días con noticias USD de alto impacto |
| **Máx. operaciones simultáneas** | 2 |
| **Máx. operaciones/día** | 5 |
| **Rotación de par** | Si cierra operación en un par, prefiere buscar siguiente entrada en par distinto |

---

## 2. Dirección / Sesgo (Tendencia Macro)

| Concepto | Regla |
|---|---|
| **Tendencia alcista** | MÁXIMOS y MÍNIMOS cada vez más altos (HH / HL) |
| **Tendencia bajista** | MÁXIMOS y MÍNIMOS cada vez más bajos (LH / LL) |
| **Cambio de tendencia** | **Rompimiento / Cambio de Estructura** (BOS/CHoCH) = precio rompe máximo/mínimo relevante en dirección contraria a tendencia previa |
| **Definición de pivotes** | **NO usa conteo de velas**. Usa **niveles fijos de apertura/cierre de cada sesión** (High/Low sesión) como referencia objetiva |
| **Jerarquía** | Tendencia se define **primero en macro (1D/4H)** → entradas buscan alineación a favor de esa tendencia |
| **Trendline diagonal** | Referencia ocasional — dibujar visiblemente, usar como **confirmación adicional** de cambio de tendencia |

---

## 3. Setup — Qué Espera Antes de Operar

| Elemento | Descripción | Regla Programable |
|---|---|---|
| **Confluencia de sesiones** | Cuando High/Low de **2-3 sesiones distintas** coinciden en mismo nivel → zona con más peso/fuerza | **SIEMPRE da más peso** a la señal (confirmado) |
| **Barrido de liquidez** | Precio rompe brevemente High/Low de sesión previa (stops) y se revierte | Base del setup |
| **Acumulación** | Fase lateral/rango pequeño en zona de confluencia antes del rompimiento/rechazo final | Componente opcional de setup |
| **Manipulación (señal buena)** | Barrido agresivo/mecha larga = trampa que precede a entrada real | Validada por **3 filtros mecánicos** (ver §4) |

---

## 4. Gatillo de Entrada (Trigger) — **REGLAS EXACTAS Y PROGRAMABLES**

### 4.1 Filtro de Cierre de Vela (Validación del Rechazo)
```
SI precio cruza nivel de soporte hacia abajo:
    ESPERAR cierre de esa vela
    SI vela cierra POR ENCIMA del nivel (deja mecha inferior) → RECHAZO / MANIPULACIÓN = SEÑAL VÁLIDA
    SI vela cierra POR DEBAJO con cuerpo sólido → ROMPIMIENTO REAL = BLOQUEAR ENTRADA
```

### 4.2 Gatillo de Reingreso / Entrada (Double Cross)
```
LA ENTRADA ES A MERCADO (market order), NO limit order
Se dispara SÍ Y SOLO SÍ ocurre DOBLE CRUCE:
    1. Precio rompe soporte hacia abajo (barrido/acción)
    2. Precio se da la vuelta y cruza ESE MISMO NIVEL de regreso HACIA ARRIBA
    → EN ESE CRUCE HACIA ARRIBA = DISPARAR ORDEN MARKET
```

### 4.3 Confirmación de Volumen (Absorción Institucional)
```
La vela que hace el falso rompimiento Y regresa al rango DEBE tener PICO DE VOLUMEN (tick volume)
→ Confirma que instituciones absorbieron las ventas
```

### 4.4 Tres Condiciones Mecánicas de Validación del Rechazo (TODAS deben cumplirse)

| # | Condición | Fórmula / Lógica |
|---|---|---|
| **1. Profundidad Máxima (ATR Filter)** | Perforación del nivel NO debe exceder **1 ATR(14)** | `penetration_pips ≤ ATR(14)_pips` → válido; `> ATR(14)` → rompimiento real → BLOQUEAR |
| **2. Anatomía de la Vela (Mecha ≥ 50% FIJO)** | Mecha inferior/superior ≥ **50%** del rango total de la vela (High - Low) | `lower_wick / (high - low) ≥ 0.50` (LONG) / `upper_wick / (high - low) ≥ 0.50` (SHORT) |
| **3. Factor Tiempo (Reclaim ≤ 2 Velas MÁXIMO)** | Precio debe cruzar de regreso y cerrar con cuerpo **POR ENCIMA/DEBAJO del nivel original** en **máx. 2 velas** tras la perforación inicial | `candles_to_reclaim ≤ 2`; `> 2` = aceptación del precio → momentum perdido → BLOQUEAR |

> **Confirmado por Mariely**: 50% fijo (no rango 40-50%), máximo 2 velas (no 3). "Si el precio no logra regresar y cerrar por encima/debajo del nivel en 2 velas máximo, el momentum se perdió y el bot debe anular la entrada."

---

## 5. Cuándo NO Entrar (Filtros Duros)

| Filtro | Regla |
|---|---|
| Volatilidad extrema | Noticias USD de alto impacto próximas (calendario económico) |
| Máx. concurrentes | 2 operaciones abiertas |
| Máx. diarias | 5 operaciones/día |
| Rotación | Tras cierre en un par → buscar siguiente en par distinto |
| Fin de semana | Cierra todo viernes, no opera sábados/domingos |
| Caída conexión | Sistema debe cerrar posición automáticamente |
| **Rechazo inválido** | Si NO cumple las 3 condiciones §4.4 → NO entrar |
| **Rompimiento real** | Si vela cierra abajo con cuerpo sólido O penetración >1 ATR → NO entrar |

---

## 6. Stop Loss

| Parámetro | Regla |
|---|---|
| **Distancia SL** | **Proporción fija 1:2 vs TP** — si TP = 90 pips → SL = 45 pips (NO basado en ATR/estructura) |
| **Breakeven** | Mueve SL a breakeven al **40% del camino al TP** (confirmado) |
| **Parciales** | Al 40% del camino al TP: mover SL a BE + cerrar fracción (ej. 0.03 → cierra 0.01, deja 0.02) |

---

## 7. Take Profit

| Parámetro | Regla |
|---|---|
| **R:R objetivo** | 1:2 fijo (arriesga 1 para ganar 2) |
| **Gestión parcial** | Asegura parte del lotaje conforme avanza (ej. 0.03 → cierra 0.01, deja 0.02 correr) hasta TP final |

---

## 8. Tamaño de Posición (Sizing) — **RESUELTO**

| Regla Elegida | **1% de riesgo por operación (Lotaje Dinámico)** |
|---|---|
| Fórmula | `Lote = (Balance × 0.01) / (SL_pips × Valor_Pip_Por_Lote)` |
| Valor pip confirmado (XAUUSD) | 0.01 lote = $1/pip; 0.10 lote = $10/pip; 1.00 lote = $100/pip |
| Ejemplo | Balance $10,000, SL 50 pips en XAUUSD → Riesgo $100 → Lote = 100 / (50 × 1) = **0.02 lotes** |

> **Regla B (0.01 lote/$1000 fijo) DESCARTADA** — no garantiza 1% riesgo real.

---

## 9. Gestión y Cierre

| Regla | Detalle |
|---|---|
| Cierre semanal | Todas las posiciones cerradas antes del fin de semana |
| Viernes | No opera viernes |
| Caída conexión | Sistema debe cerrar posición automáticamente |

---

## 10. Kill-Switch (Límites de Protección)

| Límite | Acción | Reactivación |
|---|---|---|
| **Pérdida diaria ≥ 5%** | Pausa trading el resto del día | Manual (Mariely) |
| **Pérdida mensual ≥ 30%** | Detiene sistema completo | Manual (Mariely) |
| **5 pérdidas consecutivas** | Bloquea sistema (aunque no llegue a 5% diario) | Manual (Mariely) |
| **Ámbito** | **Por cuenta individual** (confirmado) — no agregado multi-cuenta | |

---

## 11. Historial Existente

- Opera manualmente esta estrategia **desde hace 2 años**
- Tiene registro de operaciones en **MT5** (pendiente de compartir)
- Peor racha histórica: $10,000/día (cuenta personal, **antes** de gestión de riesgo actual — "no aplica")

---

## 12. Visión del Sistema (Prioridad #1)

> **"LA REGLA MÁXIMA SERÍA PRESERVAR CAPITAL"**

| Deseo | Estado |
|---|---|
| Preservación de capital > maximizar ganancia | ✅ Principio rector |
| Ir más allá de patrones de velas | ✅ Quiere: **perfil de volumen**, **order flow** |
| Distinguir entrada institucional vs retail | ✅ Objetivo (Fase 4) |
| Detectar anomalías/trampas/falsos rompimientos | ✅ **Resuelto**: 3 filtros mecánicos §4.4 |
| Redes neuronales sobre liquidez + volumen | ✅ Capa futura (Fase 4) |

---

## 13. Zonas Horarias / Sesiones — **RESUELTO**

| Sesión | Horario (México / UTC-6) | Implementación |
|---|---|---|
| **Asia** | 18:00 - 03:00 (día anterior - día actual) | Calcular High/Low en este rango |
| **Londres** | 02:00 - 11:00 | Calcular High/Low en este rango |
| **Nueva York** | 07:00 - 16:00 | Calcular High/Low en este rango |

**Implementación técnica**:
- Convertir timestamp del broker (MT5 server time) → **México (UTC-6 / UTC-5 con DST)**
- Calcular High/Low de cada sesión en ese huso
- **Dibujar niveles invisibles** (para backtester/engine) + **visibles** (para dashboard/Telegram)
- Crear **fractal de zona**: superposición de High/Low de 2-3 sesiones = zona de confluencia

---

## 14. Flechas Agrupadas en Capturas — **RESUELTO**

> **SON REFERENCIAS VISUALES** — no reentradas reales. El documento original se mantiene: "si no funciona la primera operación, no reentro".

---

## 15. Referencias de Evidencia Visual (14 capturas 24/08/2026)

| Archivo | Instrumento | Contenido Clave |
|---|---|---|
| `06d4dafc...` | XAUUSD | Precio base ~4641-4656 |
| `3b460efe...` | XAUUSD | High/Low London, NY, Asia con precios exactos |
| `3fa36391...` | XAUUSD | Session levels: High Asia 4141, High London 4085 |
| `7d86fe7b...` | XAUUSD | High NY 4371, High London 4346, Low London 4156 |
| `98735102...` | **EURUSD** | 1.1662, "MAS ALTOS FORMADOS ANTES DEL CAMBIO" |
| `bb1dcd73...` | XAUUSD | Niveles 4640, 4457, 4364 |
| `ee306204...` | XAUUSD | **Detallado**: "barrido de asia", confluencia Low Asia 4043 |
| `8367a006...` | - | Gráfico limpio (sin texto OCR) |
| `0c081072...` | - | Gráfico limpio |
| `b6d12cd6...` | - | Gráfico limpio |
| `b8581bd7...` | - | Gráfico limpio |
| `cd616351...` | - | Gráfico limpio |
| `fa36fe5f...` | - | Gráfico limpio |

---

## 16. Lista Final: **CERO Preguntas Pendientes** ✅

| # | Pregunta | **RESPUESTA** |
|---|---|---|
| **1** | Sizing | **1% riesgo/op (dinámico)** — fórmula exacta arriba |
| **2** | Breakeven/parciales | **40% del camino al TP** |
| **3** | Flechas agrupadas | **Referencias visuales únicamente** |
| **4** | Manipulación buena vs mala | **3 filtros mecánicos §4.1-4.4** (cierre vela, double cross, volumen + 3 condiciones ATR/mecha/tiempo) |
| **5** | Confluencia peso | **SIEMPRE más peso** |
| **6** | Rechazo válido | **3 condiciones §4.4** (ATR ≤1, mecha ≥50% FIJO, reclaim ≤2 velas MÁXIMO) |
| **7** | Inyección capital | **Pico de volumen en vela de falso rompimiento + retorno** |
| **8** | Zonas horarias | **México (UTC-6/UTC-5 DST)**, niveles invisibles + visibles, fractal confluencia |
| **9** | Límites agregados | **Por cuenta individual** |
| **10** | Trendline diagonal | **Referencia ocasional**, visible, confirmación adicional cambio tendencia |

---

**Fin de ESPECIFICACION_SMC.md** — **Especificación completa, sin ambigüedades, lista para codificar `specs/SMC_RULES.md` y backtester Fase 1.**