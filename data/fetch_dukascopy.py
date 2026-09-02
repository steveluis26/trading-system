"""Descarga M1 de Dukascopy (bi5) para un simbolo, ultimos N meses,
y resamplea a M5 con bid/ask -> CSV estilo del proyecto.
Formato salida: timestamp,open,high,low,close,volume  (MID = (bid+ask)/2)

Dukascopy bi5:
  https://datafeed.dukascopy.com/datafeed/{SYM}/{{YYYY}}/{{MM}}/{{DD}}/{{HH}}h_ticks.bi5
  El bi5 tiene ticks por hora; los agrupamos por dia -> M1 -> M5.
"""
from __future__ import annotations
import urllib.request, ssl, lzma, struct, os
from datetime import datetime, timedelta
import csv

SYMS = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD"}
MONTHS = 24
OUT = "data/raw"

def fetch_bi5(sym, y, m, d, h, ctx):
    url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data = urllib.request.urlopen(req, timeout=20, context=ctx).read()
    except Exception:
        return None
    try:
        raw = lzma.decompress(data)
    except Exception:
        return None
    # cada tick: 5 int (time_ms, ask*100000, bid*100000, askvol, bidvol) = 20 bytes
    ticks = []
    for i in range(0, len(raw) - 19, 20):
        t, ask, bid, av, bv = struct.unpack(">iiiiI", raw[i:i+20])
        ticks.append((t, ask, bid))
    return ticks

def month_days(y, m):
    # dias de ese mes
    if m == 12:
        nxt = datetime(y+1, 1, 1)
    else:
        nxt = datetime(y, m+1, 1)
    return (nxt - datetime(y, m, 1)).days

def download(sym, months):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    now = datetime.utcnow()
    rows = []  # (datetime, o,h,l,c,v)
    for back in range(months, -1, -1):
        dt = now - timedelta(days=back*30)
        y, m = dt.year, dt.month
        for d in range(1, month_days(y, m) + 1):
            day_ticks = []
            for h in range(24):
                tk = fetch_bi5(sym, y, m, d, h, ctx)
                if tk:
                    base = datetime(y, m, d, h)
                    for (tms, ask, bid) in tk:
                        ts = base + timedelta(milliseconds=tms)
                        day_ticks.append((ts, ask/1e5, bid/1e5))
            if not day_ticks:
                continue
            day_ticks.sort()
            # agrupar a M1
            from collections import defaultdict
            m1 = defaultdict(list)
            for ts, a, b in day_ticks:
                key = ts.replace(second=0, microsecond=0)
                m1[key].append((a, b))
            for k in sorted(m1):
                grp = m1[k]
                o = (grp[0][0]+grp[0][1])/2
                c = (grp[-1][0]+grp[-1][1])/2
                hi = max((a+b)/2 for a, b in grp)
                lo = min((a+b)/2 for a, b in grp)
                v = len(grp)
                rows.append((k, o, hi, lo, c, v))
    # resamplear M1 -> M5
    m5 = []
    for i in range(0, len(rows), 5):
        grp = rows[i:i+5]
        if not grp: continue
        t0 = grp[0][0]
        o = grp[0][1]
        c = grp[-1][4]
        hi = max(r[2] for r in grp)
        lo = min(r[3] for r in grp)
        v = sum(r[5] for r in grp)
        m5.append((t0, o, hi, lo, c, v))
    # guardar
    os.makedirs(OUT, exist_ok=True)
    fn = f"{OUT}/{sym}_5m_{months}m.csv"
    with open(fn, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","open","high","low","close","volume"])
        for r in m5:
            w.writerow([r[0].strftime("%Y-%m-%d %H:%M:%S+00:00"),
                        f"{r[1]:.10f}", f"{r[2]:.10f}", f"{r[3]:.10f}", f"{r[4]:.10f}", r[5]])
    return fn, len(m5)

if __name__ == "__main__":
    import sys
    for sym in SYMS:
        print(f"Descargando {sym} ({MONTHS} meses)...")
        fn, n = download(sym, MONTHS)
        print(f"  -> {fn}  ({n} velas M5)")
