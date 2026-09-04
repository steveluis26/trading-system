import yaml
from risk.config import RiskConfig
from pathlib import Path

def test_pip_source_is_instruments():
    cfg = RiskConfig.from_yaml()
    assert cfg.usd_per_pip("XAUUSD") == 1.0, "XAU 1.0 per 0.01 lot (instruments.yaml pip_value_per_lot)"
    assert cfg.usd_per_pip("EURUSD") == 10.0
    assert cfg.usd_per_pip("GBPUSD") == 10.0
    assert cfg.pip("XAUUSD") == 0.01
    assert cfg.pip("EURUSD") == 0.0001
    assert cfg.pip("GBPUSD") == 0.0001

def test_sizing_1pct_all_symbols():
    cfg = RiskConfig.from_yaml()
    for sym, sl, exp_vol, exp_risk in [("XAUUSD", 45, 2.22, 99.9), ("GBPUSD", 22, 0.45, 99), ("EURUSD", 20, 0.5, 100)]:
        upp = cfg.usd_per_pip(sym)
        vol = round((10000*0.01)/(sl*upp), 2)
        risk = sl*vol*upp
        assert abs(vol - exp_vol) < 0.01, f"{sym} SL{sl} vol {vol} != {exp_vol}"
        assert abs(risk - exp_risk) < 2, f"{sym} risk ${risk} != {exp_risk}"

def test_sizing_SL45_XAU():
    cfg = RiskConfig.from_yaml()
    vol = round((10000*0.01)/(45*cfg.usd_per_pip("XAUUSD")), 2)
    assert vol == 2.22 and 45*vol*1.0 == 99.9, "XAU SL45 2.22 -> $99.9 1% (pip 1.0 per 0.01)"

def test_no_duplicate_pip_value():
    inst = yaml.safe_load(open(Path("config/instruments.yaml")))
    assert inst["pip_value_usd_per_standard_lot"]["XAUUSD"] == 100.0
    assert inst["pip_value_usd_per_standard_lot"]["EURUSD"] == 10.0
    assert inst["pip_value_usd_per_standard_lot"]["GBPUSD"] == 10.0
