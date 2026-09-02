# Panel de Contexto en Tiempo Real (TradingView-style) — ALCANCE PENDIENTE

**Fuente:** Mariely pidió un panel adicional en el dashboard: Tendencia Macro,
Flujo Inmediato (VSA), Volumen (5 velas), Volatilidad (ATR), Liquidez en Radar.

**Estado:** PENDIENTE DE ALCANCE. NO entra al pipeline de trading (trigger/estrategia)
hasta que se confirme el caso A o B abajo.

## Mapeo a nuestro codigo (no a los nombres de ella)
Ella cito structure_analyzer.py / trigger_engine.py / setup_detector.py — ESOS ARCHIVOS
NO EXISTEN en trading_system (son de otra base, probablemente AuraTrade). Nuestra
logica equivalente esta en:
  - Tendencia Macro + Liquidez en Radar -> strategies/smc_multitf.py (_trend_d1, _swings, _prev_session_highlow, _sweep_check)
  - Volatilidad ATR -> NO EXISTE AUN (usamos EMA50 H1, no ATR). Hay que construir ATR(14).
  - Flujo Inmediato / VSA -> NUEVO (aprox por cierre-dentro-de-rango, no order book real).

## Caso A: SOLO INFORMATIVO (dashboard, solo lectura)
- Modulo aparte: features/realtime_panel.py (no toca strategies/ ni risk/).
- Bajo riesgo. Se hace en paralelo sin afectar lo validado.
- Calcula las 5 metricas por vela M5 y las expone al dashboard + Telegram (solo lectura).
- NO modifica trigger/reglas de entrada.

## Caso B: EL BOT LO USA PARA DECIDIR
- Regla NUEVA: hay que formalizar numeros exactos con Mariely ANTES de codigo.
  Ej: "minimo X% de flujo comprador para entrar", "ATR maximo Y para no entrar".
- Modificaria strategies/smc_multitf.py (on_bars) y posiblemente risk/config.yaml.
- Requiere: (1) ella da los umbrales, (2) backtest del nuevo filtro, (3) walk-forward.
- NO se empieza hasta tener los numeros.

## VSA (aproximacion, no order book)
En forex retail NO hay order book real. La estimacion es:
  %comprador = (close - low) / (high - low)  ponderado por volumen de la vela
  (cierre cerca del high => presion compradora; cerca del low => vendedora)
Mariely YA SABE que es estimacion. No inventar precision falsa.
Ventana: 5 velas M5 para "Volumen (5 velas)".

## Decision pendiente
Preguntar a Mariely: ¿Caso A o Caso B? Hasta que responda, esto es backlog de
dashboard, NO del motor de trading.
