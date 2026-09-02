# Reunión Mariely — 2026-09-01 (hoy 18:00, CX)

## 1. Historial de precios M5 (2+ años) — Centro de Cotizaciones MT5

### Qué necesitamos
- Instrumentos: **EURUSD, GBPUSD, XAUUSD**.
- Marco: **M5** (5 minutos), **2+ años** de historia.
- **Bid/ask reales** (no mid). La fuente que usamos hasta ahora (evtradelabs) trae bid/ask, pero para XAUUSD y GBPUSD el rango de años es limitado.
- Zona horaria de los timestamps: **México (America/Mexico_City)** o UTC con conversión explícita (queremos saber qué hora marca cada vela).

### Cómo extraerlo del Centro de Cotizaciones (MT5)
Que ella:
1. Abra MT5 → **Centro de Cotizaciones** (Market Watch).
2. En el menú: **Archivo → Guardar como...** (o "Exportar") sobre el chart M5 de cada par, para un rango de 2+ años.
3. O use **Historia de cotizaciones** (F2): seleccione cada símbolo, abra la ventana de histórica, filtre M5, rango 2+ años, y exporte a CSV.
4. Si MT5 lo permite, exporte con **bid y ask** (no solo close). Muchas exportaciones solo traen OHLC del bid o del mid — hay que verificarlo.

### Qué verificar al recibir el archivo
| Punto | Qué chequear |
|---|---|
| Rango real | Primera y última fecha. Que cumpla 2+ años por par. |
| Marcos | Que sea M5 (no H1, no ticks). Verificar saltos de tiempo entre velas (~5 min). |
| Bid/ask | Que haya columnas separadas de bid y ask (ej. `open_bid, high_bid, low_bid, close_bid, open_ask, ...`), o que el close sea bid. Si es solo mid, avisamos que es compatibilidad pero no spread real. |
| Horario | TZ de los timestamps (UTC, MX, o naive). Si es naive, pedir que nos diga la TZ. |
| Vacíos | Que no haya días/horas faltantes (fiat hours, sin datos del fin de semana). |
| Formato | CSV con cabecera o sin. Columnas consistentes entre los 3 pares. |

### Formato preferido (lo que consume nuestro backtester)
```
timestamp,open_bid,high_bid,low_bid,close_bid,open_ask,high_ask,low_ask,close_ask,volume
```
Con timestamp en **UTC** o **America/Mexico_City** (explícito). Si hay solo mid (close = (bid+ask)/2), lo aceptamos como compatible pero documentado.

### Preguntas para Mariely en la reunión
1. ¿Puede exportar M5 de 2+ años de los 3 pares directamente del Centro de Cotizaciones hoy?
2. ¿El exportado trae bid y ask separados, o solo el mid / solo el bid?
3. ¿Qué zona horaria tienen los timestamps (UTC o hora de CX)?
4. ¿Puede enviarnos el archivo por algún canal (email, drive, etc.) hoy o mañana?
5. ¿Tiene el histórico de operaciones en MT5 por separado? (Esto es para comparar contra el backtest después — no para el backtest mismo.)

## 2. Panel en tiempo real — Caso A vs Caso B (pregunta abierta)

### Estado actual
- **Caso A: construido y funcionando.** Es el panel de contexto "visual" que ya está en el dashboard:
  - Panel de 3 pares (EURUSD, GBPUSD, XAUUSD) con: tendencia D1/4H, VSA (fuerza de la vela), ATR, liquidez en radar.
  - Se actualiza en vivo desde los CSV de datos crudos (no toca la estrategia ni el risk engine).
  - Es solo lectura / visual — no genera señales ni ejecuta nada.
- **Caso B: no definido.** No hay Caso B construido ni especificado en el disco.

### La pregunta pendiente
¿Qué sería Caso B? ¿Es otra variante del panel visual (distinto set de métricas, distinta presentación)? ¿O es algo distinto (panel que sí integre algo del backtest, panel de señales, panel de contexto para la estrategia)?

**Necesito tu luz sobre:**
- ¿Caso B existía como idea previa que quedó en el aire?
- ¿Para la reunión de hoy con Mariely interesa mostrar solo Caso A (que ya está funcionando), o hay que aclarar qué sería Caso B?

### Mi posición
Creo que para hoy basta con **mostrar Caso A** (ya funciona, datos actualizados, es lo que pide "panel de contexto en tiempo real"). La pregunta Caso A vs B queda como decisión de diseño para después, no blocking para la reunión.

---

*Estado al momento de escribir: 2026-09-01. Actualizar si la reunión avanza.*
