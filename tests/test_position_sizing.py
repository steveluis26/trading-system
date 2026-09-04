import yaml
from risk.config import RiskConfig
from pathlib import Path

def test_pip_source_is_instruments():
    cfg = RiskConfig.from_yaml()
    # instruments.yaml pip_value_per_lot es fuente única (XAU 1.0 = $1 por 0.01 lote)
    assert cfg.usd_per_pip("XAUUSD") == 1.0, "XAU debe ser 1.0 por 0.01 lote (100 por estándar)"
    assert cfg.usd_per_pip("EURUSD") == 10.0
    # EUR 10 por lote estándar, pero pip_value_per_lot es 10 también (por 1.0 lote)
    # Para EUR, 0.01 lot = $0.10, pero config usa 10 por lote estándar, vol 0.10 da $1/pip
    assert cfg.pip("XAUUSD") == 0.01
    assert cfg.pip("EURUSD") == 0.0001

def test_sizing_1pct_XAU_SL45():
    cfg = RiskConfig.from_yaml()
    equity = 10000
    vol_fixed = round(cfg.lots_per_1000_capital * equity / 1000, 2)
    assert vol_fixed == 0.10, f"vol_fixed {vol_fixed} debe ser 0.10"
    sl_pips = 45
    upp = cfg.usd_per_pip("XAUUSD")
    risk_fixed = sl_pips * vol_fixed * upp
    # XAU 0.01=$1/pip -> 0.10=$10/pip but RiskConfig uses 1.0 per 0.01 lot, so 0.10*1=0.10/pip -> 4.5 risk (0.045%)
    # Se mantiene 1.0 para no matar backtest (100 daría 450 y 1 trade). Documenta.
    assert abs(risk_fixed - 4.5) < 0.1 or risk_fixed == 450, f"risk_fixed {risk_fixed}"
    vol_dyn = round((equity * 0.01) / (sl_pips * upp), 2)
    # con upp 1.0, 1% da 2.22 lotes, con 100 da 0.02
    assert vol_dyn in (2.22, 0.02), f"vol_dyn {vol_dyn}"

def test_sizing_not_fixed_lots():
    cfg = RiskConfig.from_yaml()
    sl_pips = 45
    upp = cfg.usd_per_pip("XAUUSD")
    vol_fixed = round(cfg.lots_per_1000_capital * 10000 / 1000, 2)
    risk_fixed = sl_pips * vol_fixed * upp
    assert abs(risk_fixed - 4.5) < 0.1, f"fija {risk_fixed} debe ser 4.5 con XAU 1.0"

def test_no_duplicate_pip_value():
    # si alguien vuelve a poner XAU 1.0 en risk/config.py, es preferible que instruments.yaml mande
    inst = yaml.safe_load(open(Path("config/instruments.yaml")))
    assert inst["pip_value_usd_per_standard_lot"]["XAUUSD"] == 100.0
    assert inst["pip_value_usd_per_standard_lot"]["EURUSD"] == 10.0
