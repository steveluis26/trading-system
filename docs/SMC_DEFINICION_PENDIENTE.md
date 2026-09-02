# Definición numérica de la Estrategia SMC — PROPUESTA para validación

**Propósito:** convertir las palabras de Mariely (secciones 1-4 y aclaraciones) en
reglas reproducibles. Cada parámetro es una PROPUESTA con valor SMC estándar.
Ella debe confirmar o ajustar cada uno observando sus propias marcas en gráfico.
**Sin este documento firmado, el backtester no puede correr.**

Convención de marcos (según ella):
- **D1**: tendencia macro
- **H4 / H1**: confirmar impulso (no operar retrocesos)
- **M15**: identificar zona / barrido de liquidez de la sesión
- **M5**: entrada por ruptura de estructura (BOS) + confirmación de volumen

---

## 1. Swing High / Low (pivote)

Definición: un **swing high** es un máximo cuya vela tiene `L` velas con menor
high a cada lado; un **swing low** análogo con mínimos.

| Parámetro | Propuesta | Nota |
|---|---|---|
| `pivot_left` / `pivot_right` | **3 velas** | SMC típico: 3 a 5. Usar 3 para M5 (más señales), 5 para D1. |
| Aplicación por marco | M5=3, M15=3, H1=4, H4=5, D1=5 | Marcos mayores => pivotes más anchos. |

**Pregunta para ella:** ¿usa 3 velas o más para marcar sus swings en cada marco?

---

## 2. Estructura de tendencia (D1) — sección 2

Definición reproducible de HH/HL (alcista) y LL/LH (bajista):

- Tomar los últimos **N=3 swing points** en D1.
- **Alcista** si: `swing_high[i] > swing_high[i-1]` Y `swing_low[i] > swing_low[i-1]` para los 3.
- **Bajista** si: `swing_low[i] < swing_low[i-1]` Y `swing_high[i] < swing_high[i-1]`.
- Si no cumple claramente: **NEUTRAL** → no operar ese día (no forzar dirección).

**Pregunta:** ¿considera neutral cuando no hay estructura clara, o siempre opera un lado?

---

## 3. Impulso vs Retroceso (H4/H1) — sección 3

Regla de filtro propuesta: operar SOLO en dirección del impulso.

- Calcular pendiente de **EMA(50) en H1** (o estructura H4).
- Sesgo compra solo si `close_H1 > EMA50_H1` Y estructura H4 no es bajista.
- Sesgo venta solo si `close_H1 < EMA50_H1` Y estructura H4 no es alcista.
- "Impulso" = precio rompe el último swing en la dirección de la tendencia D1.

**Pregunta:** ¿usa alguna media o solo estructura pura para decidir impulso?

---

## 4. Barrido de liquidez (M15) — sección 3

Definición propuesta:

1. Marcar el **high y low de la sesión previa** (Londres 08-17 UTC, NY 13-22 UTC).
2. En M15, detectar que el precio **toma** ese high/low:
   - Toma de liquidez alcista: `low_M15 <= session_low - tolerance` (barrido del mínimo).
   - Esto genera sesgo de compra (espera que NY vaya a buscar el alto dejado).
3. **Reversa medible**: tras el barrido, el precio debe revertir al menos
   `rev_pips` en las siguientes `rev_bars` velas M15 para contar como "barrido válido".

| Parámetro | Propuesta | Nota |
|---|---|---|
| `tolerance` | 1 pip (forex) / 10 pips (XAUUSD) | margen sobre el nivel |
| `rev_pips` | 5 pips (forex) / 30 pips (XAUUSD) | reversa minima |
| `rev_bars` | 4 velas M15 (1h) | ventana de confirmación |

**Pregunta:** ¿el barrido cuenta solo por el take del nivel, o exige la reversa?

---

## 5. Entrada BOS (M5) — aclaración 3

Jerarquía confirmada: **(1) BOS en M5 = disparador, (2) volumen = confirmación**.

Definición de BOS propuesta:
- En M5, tras sesgo de compra, el precio debe cerrar **por encima** del último swing high M5 (rompimiento de estructura).
- **Por cierre de vela** (no intradía) → evita falsos breaks por ruido.

| Parámetro | Propuesta |
|---|---|
| Confirmación BOS | **cierre de vela M5** rompe el swing opuesto |
| Volumen (Fase 4) | requerir volumen > media(20) en la vela de ruptura — solo si hay feed; si no, BOS basta |

**Pregunta:** ¿BOS por cierre de vela o por rompimiento intradía?

---

## 6. Salida / Gestión (secciones 6,7 + aclaración 5)

- **SL** = mitad de la distancia entry→TP (R:R 1:2), o 1:3 si aplica.
- **Breakeven + parcial**: a **40% del camino al TP** → SL a breakeven Y cerrar 1/3 del lotaje.
  - Ejemplo ella: 0.03 → cierra 0.01 (queda 0.02 con SL en breakeven).
- **TP** = 2x o 3x SL.
- **Sin hold fin de semana**: cerrar antes del cierre de viernes (17:00 NY / 21:00 UTC).

---

## 7. Filtros (secciones 5,10)

- "Muy volátil" = **noticias HIGH impact USD** → no abrir en ventana ±2h de la noticia.
- Máx 2 abiertas, máx 1 por símbolo, máx 5 ops/día.
- 5 pérdidas seguidas → **bloqueo total** (reactivación manual).
- 5% pérdida diaria → parar el día. 30% mensual → STOP total.

---

## CHECKLIST de validación (ella marca OK/ajusta)

- [ ] Swing pivots: M5/M15 = 3 velas, H1 = 4, H4/D1 = 5
- [ ] Tendencia D1: 3 swings, HH/HL o LL/LH; neutral si ambiguo
- [ ] Impulso H1: close > EMA50 (¿usa EMA o solo estructura?)
- [ ] Liquidez M15: take de high/low sesión ± tolerancia + reversa 5/30 pips en 4 velas
- [ ] BOS M5: por cierre de vela (¿intradía o cierre?)
- [ ] R:R: SL = 1/2 distancia a TP; TP 1:2 o 1:3
- [ ] Breakeven/parcial: a 40% al TP
- [ ] Filtro noticias: HIGH impact USD ±2h
