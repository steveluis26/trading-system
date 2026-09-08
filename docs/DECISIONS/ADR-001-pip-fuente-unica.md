# ADR-001 — Fuente única pip_value_usd_per_standard_lot
**Fecha:** 2026-09-03
**Estado:** Aceptado
**Contexto:** instruments.yaml tenía pip_value_per_lot: 1.0 (per 0.01) y pip_value_usd_per_standard_lot: 100.0 (per 1.0) — risk/config.py leía el primero (1.0) por error 100× (2.22 lotes vs 0.022).
**Decisión:** risk/config.py lee pip_value_usd_per_standard_lot (XAU 100, EUR/GBP 10). pip_value_per_lot renombrado a pip_value_per_microlot (solo referencia).
**Consecuencia:** XAU SL45 0.02 / $90 0.90% (lot_step 0.01) — test lee de yaml, no hardcodea.
