# Lo que necesito antes de escribir la estrategia real

## BLOQUEANTE 1 — Especificación de la estrategia (una, no las 4)
Llenar `docs/ESPECIFICACION_ESTRATEGIA.md`. **Empezar por UNA sola.**

**Criterio de aceptación:** dos personas leyendo la especificación por separado
producen exactamente las mismas señales sobre el mismo gráfico. Si dice
"cuando el precio respeta la zona" no está terminada; si dice
"cuando close > EMA(200) y el low toca el FVG identificado como
[definición numérica] dentro de las siguientes 5 velas", sí.

Sin esto no se puede codear `strategies/`. No hay forma de adivinar.

## BLOQUEANTE 2 — Datos históricos
- **Instrumento(s)** exactos y **timeframe** de señal + contexto.
- Fuente: idealmente export del **mismo broker** donde se operará
  (Vantage/VT Markets) porque el spread y el feed difieren entre brokers.
- Formato: OHLC **con spread por vela** (o bid y ask separados). Solo mid = inútil.
- Periodo: mínimo **3-5 años**, incluyendo 2020 y 2022 (regímenes distintos).
- Cómo: MT5 > Ver > Símbolos > pestaña Barras/Ticks > Exportar. O Dukascopy
  (gratis, tick con bid/ask) para research inicial.

## BLOQUEANTE 3 — Parámetros de riesgo
Sección 10 de la especificación: % de riesgo por operación, drawdown máximo,
pérdida diaria máxima, máximo de posiciones, distancia mínima entre
operaciones (anti-hedging), horarios operables.
Van en `config/risk.yaml`, no en código.

## NO BLOQUEANTE pero muy valioso
- **Su historial de trading** (manual o de AuraTrade): es la única evidencia
  empírica de que la estrategia tiene algo. Se usa como referencia para
  comparar contra el backtest, no como base del sistema nuevo.
- Acceso de lectura al código/repo existente: para no repetir errores
  ya resueltos (ej. el rate limit de MetaApi).

## Preguntas técnicas a cerrar con ella
1. ¿Qué timeframe realmente? (evidencia observada en su otro sistema: H1/H4).
   Esto cierra el tema "milisegundos": no aplica.
2. ¿Un instrumento o varios? Con solo EURUSD en H1 hay ~900 eventos/año:
   pocos para entrenar. Puede requerir más pares o bajar timeframe en research.
3. ¿La estrategia es la misma que ya opera, o una nueva sin historial?
4. ¿Qué parte de su decisión es discrecional / "a criterio"? — esta respuesta
   es la más valiosa: es exactamente donde entra el ML como filtro (meta-labeling).
