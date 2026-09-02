"""Descarga M5 de evtradelabs.com (2020-2026) para EURUSD/GBPUSD/XAUUSD.
Formato: ts,o,h,l,c,ao,ah,al,ac (bid/ask REALES). Convierte a data/raw/<SYM>_5m_<anio>.csv
en formato del proyecto: timestamp,open,high,low,close,volume
El volumen en este feed es 0 (forex retail no reporta vol real) -> lo dejamos 0 y el
backtester usa ATR/volumen relativo, no absoluto.
"""
from __future__ import annotations
import urllib.request, ssl, gzip, json, csv, os
from datetime import datetime, timezone

SYMS = ["EURUSD", "GBPUSD", "XAUUSD"]
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
OUT = "data/raw"
BASE = "https://evtradelabs.com/api/simulator/data"
PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "XAUUSD": 0.01}

def fetch(sym, year):
    url = f"{BASE}/{sym}/M5/{year}.json.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    raw = urllib.request.urlopen(req, timeout=40, context=ctx).read()
    return json.loads(gzip.decompress(raw))

def to_csv(sym, year, data, pip):
    fn = f"{OUT}/{sym}_5m_{year}.csv"
    # usar MID = (bid+ask)/2 para OHLC, spread real por vela se guarda aparte si hace falta
    rows = []
    for r in sorted(data, key=lambda x: x["ts"]):
        t = datetime.fromtimestamp(r["ts"], tz=timezone.utc)
        o = (r["o"] + r["ao"]) / 2; h = (r["h"] + r["ah"]) / 2
        l = (r["l"] + r["al"]) / 2; c = (r["c"] + r["ac"]) / 2
        rows.append((t.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                     f"{o:.5f}", f"{h:.5f}", f"{l:.5f}", f"{c:.5f}", 0))
    with open(fn, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    return fn, len(rows)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for sym in SYMS:
        for y in YEARS:
            try:
                d = fetch(sym, y)
                fn, n = to_csv(sym, y, d, PIP[sym])
                print(f"  {sym} {y}: {n} velas -> {fn}", flush=True)
            except Exception as e:
                print(f"  {sym} {y} FAIL: {repr(e)[:80]}", flush=True)
    print("DONE")
