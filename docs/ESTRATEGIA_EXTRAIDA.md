# Estrategia extraída — análisis de arquitecto

Fuente: encuesta "Mi estrategia explicada" contestada por Mariely (2026-08).
Estado: BORRADOR para validar. No es código hasta resolver las banderas rojas.

## A. Lo que SÍ es codificable HOY (Fase 1)

### Multi-timeframe (MTF) — requiere motor multi-marco
- **D1**: tendencia (estructura: HH+HL alcista, LL+LH bajista)
- **H4 / H1**: confirmar impulso vs retroceso. Solo operar IMPULSOS, nunca contra tendencia.
- **M15**: buscar que el precio "liquide" el alto/bajo de la sesión previa
  (Londres deja bajo → NY lo barre → esperar confirmación M15 para compra).
- **M5**: ruptura de estructura (BOS) = entrada.
- Orden de mercado inmediata.

### Risk engine (secciones 5,6,7,8,9,10)
- 1% por operación, máx 2 abiertas, máx 5/día, máx 1 por símbolo.
- SL = mitad de la distancia al TP (R:R 1:2). Breakeven al ir a favor.
- Cierre parcial 50% cuando el precio va 50% hacia TP.
- 5% pérdida diaria → parar el día. 30% mensual → STOP total (reactivación manual).
- Sin operar viernes, sin posiciones sobre fin de semana.
- Si se cae plataforma con posición abierta → cerrar.

## B. BANDERAS ROJAS (resolver ANTES de backtest)

### B.1 Inconsistencia de lotaje vs riesgo  ⚠️
- Declara: riesgo 1%/op, LOTES = 0.01 por cada $1000, SL 45 pips si TP 90 pips.
- Con $10,000: su fórmula da 0.10 lotes. Riesgo real a 45 pips EURUSD =
  0.10 × $10/pip × 45 = **$45 = 0.45%** (no 1%).
- Para arriesgar 1% ($100) con SL 45 pips → **0.22 lotes**.
- **Resolución:** el motor dimensiona por `riesgo% × equity / distancia_SL`.
  Ignorar la fórmula de lotes. Confirmar con ella que el tamaño correcto
  es por riesgo, no por la regla de 0.01/$1000.

### B.2 "Peor racha: $10,000 en 1 día"  ⚠️⚠️
- Una pérdida de $10k/día es incompatible con 1% riesgo + 5 ops/día + 5% límite diario.
- O el $10k fue en una cuenta mucho mayor, o su disciplina real NO siguió sus
  propias reglas. **Esto es lo más importante de verificar con su historial MT5.**
- El historial MT5 dirá la verdad: si sus ops reales respetan 1%/5%/30%.

### B.3 XAUUSD (oro) en el mismo marco que forex  ⚠️
- Oro: spread ~35 puntos, rangos de 100-300 pips/día, comportamiento de sesión
  distinto a EURUSD/GBPUSD.
- "TP 90 pips / SL 45" no escala igual al oro. Necesita parámetros propios
  (SL/TP, spread, tamaño) por instrumento, no globales.

## C. La sección 12 vs la sección 1-11 (la trampa grande)

La secciones 1-11 describen una estrategia SMC (Smart Money Concepts) de
precio puro: estructura, BOS, barrido de liquidez. **Eso se puede codificar y
backtestear HOY** con OHLC + spread.

La sección 12 pide otra cosa: "redes neuronales, liquidez, perfil de volumen,
INYECCIÓN DE CAPITAL, distinguir entrada retail de institucional, anomalías,
trampas, manipulación".

**Esto requiere ORDER FLOW / DOM / footprint — datos que MT5 retail estándar
(Vantage/VT) y Dukascopy NO entregan.** Sin esos datos, "detección de inyección
de capital" y "distinguir retail de institucional" no se pueden ni definir ni
backtestear. Es una visión, no una especificación.

**Decisión de arquitectura:** Fase 1 = validar la SMC (1-11) con backtest
honesto. Fase 3 = meta-labeling ML sobre esas señales (estadístico, no order
flow). La "detección de manipulación / order flow" queda como investigación
Fase 4+, CONDICIONAL a conseguir un feed de order flow real (no es gratis ni
estándar). No construir Fase 1 alrededor de una capacidad que hoy no existe.

## D. Qué necesito de datos (confirmar con lo que ya tiene)
- 3 pares: **EURUSD, GBPUSD, XAUUSD**
- Timeframes: **D1, H4, H1, M15, M5** (resamplear desde M1/M5).
- Por vela: OHLC **+ spread (bid/ask separados)** + volumen.
- Mínimo 3-5 años, incluyendo 2020 y 2022.
- Fuente ideal: mismo broker (Vantage/VT). Si no, Dukascopy tick/OHLC.
- **Su historial MT5 real** (sección 11) = ground truth para validar contra el backtest.

## E. Preguntas de clarificación (máx 4)
1. Breakeven: ¿cuándo exactamente mueve SL a entry? ¿En cuanto el precio pasa
   entry + spread, o a un % del camino al TP? (necesario para codificar)
2. Confirmación M15/M5: ¿el BOS se define por cierre de vela o por rompimiento
   intradía? (cambiar horario el backtest)
3. Sesiones: ¿opera el solapamiento Londres-NY (13:00-17:00 UTC) o ambas por
   separado? ¿Hasta qué hora cierra nuevas entradas?
4. ¿El historial MT5 que tiene es de cuenta real o demo, y de qué tamaño?
   (para interpretar la pérdida de $10k)

## F. CLARIFICACIONES (videollamada + 7 preguntas, 2026-08)

Se resolvieron las banderas. Resumen:

### F.1 Sizing — YA NO ambiguo
CONFIRMA que usa la **formula de lotes**, no la de 1%:
- Oro: 0.01 lote = $1 por pip (pip = ultimos 3 digitos). 0.01 lote por cada $1,000.
- EURUSD/GBPUSD: 0.01 lote = $0.10 por pip.
- Riesgo efectivo real ~2% a SL de 20-40 pips (no 1%). El motor dimensiona por
  la regla de lotes y reporta el % efectivo.

### F.2 TP — concretado
TP = **2x o 3x la distancia al SL** (R:R 1:2 o 1:3). Marca los high/low de
apertura/cierre de sesion para identificar donde se "lleva mas capital"
(liquidez barrida).

### F.3 Entrada — jerarquia clara
1) BOS en M5 (ruptura de estructura) = DISPARADOR.
2) Volumen / order flow = CONFIRMACION (vacio o inyeccion de capital).
Fase 1: BOS solo (sin feed de order flow). Fase 4: anadir confirmacion de volumen.

### F.4 Volatilidad
"Muy volatil" = dias de noticias fuertes del dolar -> NO entrar.
=> filtro de noticias high-impact USD (codificable con calendario economico).

### F.5 Breakeven + parciales — concretado
A **40% del camino al TP**: mover SL a breakeven Y empezar parciales.
Ejemplo: posicion 0.03 -> cerrar 0.01 (queda 0.02) -> SL a breakeven.
El remanente 0.02 llega al TP sin riesgo.

### F.6 Perdidas consecutivas -> BLOQUEO
**5 operaciones PERDEDORAS seguidas => el sistema se BLOQUEA** (no solo pausa el dia).
CORRIGE el yaml anterior que decia 2 y "pausa dia". Es bloqueo total.

### F.7 La perdida de $10,000 — RESUELTA (bandera roja #2 cerrada)
Fue **antes** de tener gestion de riesgo, en cuenta personal de ella, y **no aplica**
a este proyecto. No es contradiccion de sus reglas actuales. Se descarta como riesgo.

### F.8 SIN historial MT5
Ella NO tiene el historial exportado. => NO hay ground truth de sus operaciones.
La unica validacion es el backtest de las reglas SMC. (Refuerza la importancia
de la Fase 1 honesta y del walk-forward.)

## G. Lo que TODAVIA es ambiguo (requiere definicion, no adivinar)

Unica bandera abierta: **las definiciones exactas de estructura SMC**.
Necesitamos, en codigo reproducible (no adjetivos):
- Swing high/low: numero de velas de cada lado para el pivote (ej. 3 a 5).
- HH/HL (alcista) y LL/LH (bajista): sobre que marco (D1) y con que tolerancia.
- BOS en M5: rompimiento del ultimo swing opuesto por CIERRE de vela, o intradia.
- Liquidez barrida: toma del high/low de la sesion previa (Londres/NY) seguida de
  reversa measurable (cuantos pips / velas).
- Impulso vs retroceso en H4/H1: regla de filtro (ej. precio > EMA, o estructura).

Estas se implementan como SMC estandar en Fase 1 y ella valida contra sus
marcas en grafico. Sin esto, el backtester no puede correr todavia.
