"""Estrategia de EJEMPLO (cruce de medias + ATR) para verificar el pipeline.
NO es la estrategia de Mariely. Se borra cuando llegue la especificacion real."""
from __future__ import annotations
from core.types import Bar, Signal, Side
from strategies.base import Strategy

class ExampleMA(Strategy):
    name = "example_ma"
    def __init__(self, fast=20, slow=50, atr=14, sl_mult=1.5, rr=2.0):
        self.f, self.s, self.a, self.m, self.rr = fast, slow, atr, sl_mult, rr

    def on_bar(self, bar: Bar, history: list[Bar]) -> Signal | None:
        if len(history) < self.s + 2: return None
        c = [x.close for x in history]
        f_now = sum(c[-self.f:]) / self.f
        s_now = sum(c[-self.s:]) / self.s
        f_prev = sum(c[-self.f-1:-1]) / self.f
        s_prev = sum(c[-self.s-1:-1]) / self.s
        if f_prev <= s_prev and f_now > s_now:   side = Side.BUY
        elif f_prev >= s_prev and f_now < s_now: side = Side.SELL
        else: return None

        w = history[-self.a:]
        atr = sum(max(x.high-x.low, abs(x.high-p.close), abs(x.low-p.close))
                  for p, x in zip(w, w[1:])) / max(len(w)-1, 1)
        if atr <= 0: return None
        e = bar.close
        sl = e - self.m*atr if side is Side.BUY else e + self.m*atr
        tp = e + self.rr*abs(e-sl) if side is Side.BUY else e - self.rr*abs(e-sl)
        return Signal(time=bar.time, symbol=bar.symbol, side=side, entry=e,
                      sl=sl, tp=tp, strategy=self.name,
                      context={"atr": atr, "spread": bar.spread})
