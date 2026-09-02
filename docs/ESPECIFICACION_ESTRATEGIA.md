# Especificación de Estrategia

**Estrategia:** ____________________  **Versión:** ____  **Fecha:** ____

> Criterio de aceptación: dos personas leyendo esto por separado deben
> producir las MISMAS señales sobre el mismo gráfico. Cada bloque mapea 1:1
> a `strategies/template.py`.

## 1. Universo
- Instrumentos: ____________________
- Timeframe de señal: ______  Timeframes de contexto: ______
- Sesiones/horarios operables (con zona horaria): ____________________
- Días/fechas excluidos (noticias, festivos, viernes tarde): ____________________

## 2. Contexto / sesgo direccional  → `_bias()`
¿Cómo se determina la dirección permitida? Paso a paso, cuantificado:
```
```
Indicadores exactos con parámetros (ej. EMA(200), ATR(14), volumen > X):
```
```
Definición operativa de estructura (BOS / CHoCH / tendencia):
```
```

## 3. Setup — condición necesaria previa  → `_setup()`
Cómo se identifica numéricamente la zona/nivel (FVG, order block, liquidez):
```
```
- Velas de validez del setup: ______   ¿Cómo se invalida? ______

## 4. Gatillo de entrada  → `_trigger()`
Debe ser **binario y verificable en la vela t**:
```
```
- Tipo de orden: [ ] market  [ ] limit  [ ] stop   Precio: ____________
- ¿Reentradas permitidas? ____  ¿Cuántas por setup? ____

## 5. Filtros de rechazo (excluir aunque el gatillo se cumpla)
- Spread máximo: ____ puntos
- ATR mínimo: ____   ATR máximo: ____
- Distancia mínima a operación previa: ____ pips
- Máximo posiciones simultáneas: ____  Por instrumento: ____
- Otros: ____________________

## 6. Stop Loss  → fórmula exacta
```
(ej. "estructura anterior - 1.5*ATR(14)", NO "debajo del soporte")
```
- ¿Se mueve? [ ] no  [ ] breakeven a ____  [ ] trailing: regla ____________

## 7. Take Profit  → fórmula exacta
```
```
- R:R objetivo: ____  ¿Salidas parciales? ____% en ____R

## 8. Position sizing
- Riesgo por operación: ____% del capital
- Fórmula de lotaje: ____________________
- Riesgo simultáneo agregado máximo: ____%

## 9. Gestión y cierre
- Tiempo máximo en posición: ______
- Cierre por evento (noticia, fin de sesión, fin de semana): ____________________
- ¿Qué hacer si la conexión se cae con posición abierta? ____________________

## 10. Límites de protección (kill-switch) → `config/risk.yaml`
- Pérdida diaria máxima → pausar: ____%
- Drawdown máximo → detener: ____%
- Pérdidas consecutivas → pausar el día: ____
- ¿Quién reactiva y bajo qué criterio? ____________________

## 11. Historial existente
- ¿Desde cuándo se opera manualmente? ______
- Win rate observado: ____%  R:R promedio: ____
- Peor drawdown vivido: ____%  Nº aproximado de operaciones: ____
- ¿Registro disponible? (Excel / MyFxBook / historial MT5) → adjuntar

## 12. Ambigüedades declaradas  ← la sección más valiosa
¿Qué parte de la decisión es discrecional, "a criterio", o difícil de escribir?
```
```
> Aquí es exactamente donde entra el ML: las reglas generan los eventos
> candidatos y el modelo predice P(TP antes que SL) como filtro. No se le
> pide al modelo inventar señales, se le pide filtrar las de ella.
