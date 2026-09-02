#!/usr/bin/env python3
"""
Yahoo Finance Historical Data Downloader
Descarga datos de yfinance para XAUUSD (via GC=F), EURUSD, GBPUSD.
Convierte a CSV listo para data_loader.py con columnas estándar.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys


SYMBOL_MAP = {
    "XAUUSD": "GC=F",     # Gold futures - más líquido y con historial largo
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
}


def download_symbol(symbol: str, yf_symbol: str, timeframe: str, period: str = "2y") -> pd.DataFrame:
    """Descarga un símbolo desde yfinance usando period."""
    print(f"  Descargando {symbol} ({yf_symbol}) {timeframe} (period={period})...")
    
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(
            period=period,
            interval=timeframe,
            auto_adjust=False
        )
        
        if df.empty:
            print(f"    ⚠️ Sin datos para {symbol} {timeframe}")
            return pd.DataFrame()
        
        # Normalizar columnas
        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        
        # Renombrar a estándar interno
        col_map = {
            "datetime": "timestamp",
            "date": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        df.rename(columns=col_map, inplace=True)
        
        # Asegurar timestamp UTC
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        
        # Seleccionar solo columnas necesarias
        keep_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        df = df[keep_cols].dropna()
        
        print(f"    ✅ {len(df):,} filas")
        return df
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return pd.DataFrame()


def resample_dataframe(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """Resamplea un DataFrame 1h a timeframe superior."""
    if df.empty:
        return df
    
    df = df.copy()
    df.set_index("timestamp", inplace=True)
    
    # Regla de resampleo
    rule_map = {
        "4h": "4h",
        "1d": "1D",
        "15m": "15min",
        "5m": "5min",
    }
    rule = rule_map.get(target_tf)
    if not rule:
        return df
    
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    
    resampled = df.resample(rule).apply(ohlc).dropna()
    resampled.reset_index(inplace=True)
    
    print(f"    📊 Resampleado a {target_tf}: {len(resampled):,} filas")
    return resampled


def main():
    print("📥 Yahoo Finance Historical Data Downloader")
    print("=" * 50)
    
    print(f"💱 Símbolos: {list(SYMBOL_MAP.keys())}")
    print(f"⏱️  Timeframes: 1h, 1d, 4h, 15m, 5m")
    print()
    
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Descargar timeframes base usando period="2y"
    base_timeframes = ["1h", "1d"]
    all_files = []
    
    for symbol, yf_symbol in SYMBOL_MAP.items():
        for tf in base_timeframes:
            df = download_symbol(symbol, yf_symbol, tf, period="2y")
            if not df.empty:
                output_file = output_dir / f"{symbol}_{tf}_2y.csv"
                df.to_csv(output_file, index=False)
                all_files.append(output_file)
                print(f"    💾 Guardado: {output_file.name}")
            print()
    
    # 5m: solo últimos 60 días (límite yfinance)
    print("🔄 Descargando 5m (últimos 60 días)...")
    for symbol, yf_symbol in SYMBOL_MAP.items():
        df_5m = download_symbol(symbol, yf_symbol, "5m", period="60d")
        if not df_5m.empty:
            output_file = output_dir / f"{symbol}_5m_60d.csv"
            df_5m.to_csv(output_file, index=False)
            all_files.append(output_file)
            print(f"    💾 Guardado: {output_file.name}")
        print()
    
    # Resamplear a timeframes derivados desde 1h
    print("🔄 Resampleando timeframes derivados desde 1h...")
    for symbol in SYMBOL_MAP.keys():
        files_1h = list(output_dir.glob(f"{symbol}_1h_*.csv"))
        if not files_1h:
            print(f"    ⚠️ No hay datos 1h para {symbol}, saltando resampleo")
            continue
        
        df_1h = pd.read_csv(files_1h[0])
        df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], utc=True)
        
        for target_tf in ["4h", "15m"]:
            df_resampled = resample_dataframe(df_1h, target_tf)
            if not df_resampled.empty:
                output_file = output_dir / f"{symbol}_{target_tf}_2y.csv"
                df_resampled.to_csv(output_file, index=False)
                all_files.append(output_file)
                print(f"    💾 Guardado: {output_file.name}")
        print()
    
    # Resumen
    print("=" * 50)
    print("✅ Descarga completada")
    print(f"📁 Archivos en: data/raw/")
    for f in sorted(output_dir.glob("*.csv")):
        size_mb = f.stat().st_size / (1024 * 1024)
        rows = sum(1 for _ in open(f)) - 1
        print(f"  {f.name}: {rows:,} filas, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()