# KNOWN_ISSUES

- Wyckoff volumen/TP fib/sesiones como peso no veto (12tr, no es Wyckoff real) — `wyckoff_v2.py:184,231`
- v4 sesiones hardcode 0-7/7-11 vs spec 02-11 (`smc_multitf.py:62` vs `sessions.yaml:7`), D1 pivotes velas `L=3,R=3` vs sesión, Double Cross 1 vela vs 2, volumen 0 líneas
- Sizing: `backtest/multitf.py:222` 1% dinámico vs `backtester/position_simulator.py` aún `lots_per_1000` fijo — 2 stacks con sizing distinto (no canónico global)
- Pip: `config/instruments.yaml` tiene `pip_value_per_lot 1.0` (microlote) + `pip_value_usd_per_standard_lot 100.0` (DEPRECATED duplicado) — `risk/config.py` ahora lee `standard_lot` (100) pero test legacy `test_config_loader.py:46` espera `1.0` — conflicto pendiente
- Tests: `tests/test_config_loader.py:46` espera `pip_value_per_lot 1.0` vs `tests/test_position_sizing.py` espera `pip_value_usd_per_standard_lot 100.0` — 2 generaciones con semántica distinta
- `core/types.py:16` `Position.pnl` defaults `usd_per_pip=10 pip_size=0.0001` hardcodeados — debe auditarse `pip_size/pip_value/contract_size/tick_size/spread/commission/swap` en todos los lugares donde se calculan
