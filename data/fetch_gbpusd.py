"""Re-descarga SOLO GBPUSD M5 24m (EURUSD ya esta listo).
Con logging de fallos para diagnosticar por que quedo vacio antes.
"""
from __future__ import annotations
import urllib.request, ssl, lzma, struct, os, csv
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SYM = "GBPUSD"
MONTHS = 24
OUT = "data/raw"
WORKERS = 16

def fetch_bi5(args):
    sym, y, m, d, h, ctx = args
    url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
    try:
        data = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
            timeout=15, context=ctx).read()
        raw = lzma.decompress(data)
        ticks = []
        for i in range(0, len(raw) - 19, 20):
            t, ask, bid, av, bv = struct.unpack(">iiiiI", raw[i:i+20])
            ticks.append((t, ask, bid))
        return (y, m, d, h, ticks, len(ticks))
    except Exception as e:
        return (y, m, d, h, None, 0)

def month_days(y, m):
    nxt = datetime(y+1, 1, 1) if m == 12 else datetime(y, m+1, 1)
    return (nxt - datetime(y, m, 1)).days

def download():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    now = datetime.now()
    jobs = []
    for back in range(MONTHS, -1, -1):
        dt = now - timedelta(days=back*30)
        y, m = dt.year, dt.month
        for d in range(1, month_days(y, m) + 1):
            for h in range(24):
                jobs.append((SYM, y, m, d, h, ctx))
    day_ticks = defaultdict(list)
    done = 0; failed = 0; got = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(fetch_bi5, j) for j in jobs]
        for fut in as_completed(futs):
            y, m, d, h, ticks, n = fut.result()
            done += 1
            if ticks:
                got += 1
                base = datetime(y, m, d, h)
                for (tms, ask, bid) in ticks:
                    ts = base + timedelta(milliseconds=tms)
                    day_ticks[(y, m, d)].append((ts, ask/1e5, bid/1e5))
            else:
                failed += 1
            if done % 500 == 0:
                print(f"  [{SYM}] {done}/{len(jobs)} ok={got} fail={failed}", flush=True)
    print(f"RESUMEN: ok={got} fail={failed} dias_con_datos={len(day_ticks)}")
    m1 = []
    for key in sorted(day_ticks):
        grp = sorted(day_ticks[key])
        by_min = defaultdict(list)
        for ts, a, b in grp:
            k = ts.replace(second=0, microsecond=0)
            by_min[k].append((a, b))
        for k in sorted(by_min):
            g = by_min[k]
            o = (g[0][0]+g[0][1])/2; c = (g[-1][0]+g[-1][1])/2
            hi = max((a+b)/2 for a, b in g); lo = min((a+b)/2 for a, b in g)
            m1.append((k, o, hi, lo, c, len(g)))
    m5 = []
    for i in range(0, len(m1), 5):
        g = m1[i:i+5]
        if not g: continue
        t0 = g[0][0]; o = g[0][1]; c = g[-1][4]
        hi = max(r[2] for r in g); lo = min(r[3] for r in g); v = sum(r[5] for r in g)
        m5.append((t0, o, hi, lo, c, v))
    os.makedirs(OUT, exist_ok=True)
    fn = f"{OUT}/{SYM}_5m_24m.csv"
    with open(fn, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","open","high","low","close","volume"])
        for r in m5:
            w.writerow([r[0].strftime("%Y-%m-%d %H:%M:%S+00:00"),
                        f"{r[1]:.10f}", f"{r[2]:.10f}", f"{r[3]:.10f}", f"{r[4]:.10f}", r[5]])
    return fn, len(m5)

if __name__ == "__main__":
    print(f"Re-descargando {SYM} (24 meses)...")
    fn, n = download()
    print(f"  -> {fn} ({n} velas M5)")
