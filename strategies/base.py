"""Contrato de estrategia (multi-timeframe).
on_bars recibe un dict {Timeframe: [Bar cerradas hasta t]} y el instante t.
La estrategia NO sabe de broker, no calcula lotaje, no decide ejecucion."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from core.types import Bar, Signal, Timeframe

class Strategy(ABC):
    name: str = "unnamed"

    @abstractmethod
    def on_bars(self, ctx: dict[Timeframe, list[Bar]], t: datetime) -> Signal | None:
        ...

    def reset(self) -> None:
        pass
