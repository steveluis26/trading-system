"""PLANTILLA: copiar por cada estrategia de Mariely.
Cada seccion corresponde 1:1 a la especificacion que ella debe llenar
(docs/ESPECIFICACION_ESTRATEGIA.md). Si un bloque no se puede escribir en
codigo, la especificacion esta incompleta -> devolverla, no adivinar."""
from __future__ import annotations
from core.types import Bar, Signal, Side
from strategies.base import Strategy

class PlantillaEstrategia(Strategy):
    name = "plantilla"

    def __init__(self, atr_period: int = 14, sl_atr_mult: float = 1.5,
                 rr: float = 2.0, min_atr: float = 0.0, max_spread: float = 999):
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.min_atr = min_atr
        self.max_spread = max_spread

    def on_bar(self, bar: Bar, history: list[Bar]) -> Signal | None:
        if len(history) < self.atr_period + 2:
            return None

        # --- 5. FILTROS DE RECHAZO (antes de todo, barato) ---
        if bar.spread > self.max_spread:
            return None
        atr = self._atr(history)
        if atr < self.min_atr:
            return None

        # --- 2. CONTEXTO / SESGO --------------------------------------
        bias = self._bias(history)          # TODO: reglas de ella
        if bias is None:
            return None

        # --- 3. SETUP -------------------------------------------------
        if not self._setup(bar, history, bias):   # TODO
            return None

        # --- 4. GATILLO ------------------------------------------------
        if not self._trigger(bar, history, bias): # TODO
            return None

        # --- 6/7. SL y TP: formula exacta, no "debajo del soporte" -----
        entry = bar.close
        if bias is Side.BUY:
            sl = entry - self.sl_atr_mult * atr
            tp = entry + self.rr * (entry - sl)
        else:
            sl = entry + self.sl_atr_mult * atr
            tp = entry - self.rr * (sl - entry)

        return Signal(time=bar.time, symbol=bar.symbol, side=bias,
                      entry=entry, sl=sl, tp=tp, strategy=self.name,
                      context={"atr": atr, "spread": bar.spread})

    # ---- helpers (implementar con las reglas reales) ----
    def _atr(self, h: list[Bar]) -> float:
        w = h[-self.atr_period:]
        return sum(max(b.high-b.low, abs(b.high-p.close), abs(b.low-p.close))
                   for p, b in zip(w, w[1:])) / max(len(w)-1, 1)

    def _bias(self, h: list[Bar]) -> Side | None:
        raise NotImplementedError("Seccion 2 de la especificacion")

    def _setup(self, bar: Bar, h: list[Bar], bias: Side) -> bool:
        raise NotImplementedError("Seccion 3 de la especificacion")

    def _trigger(self, bar: Bar, h: list[Bar], bias: Side) -> bool:
        raise NotImplementedError("Seccion 4 de la especificacion")
