#!/usr/bin/env python3
"""
Dukascopy Historical Data Downloader
Descarga datos tick/velas gratis de Dukascopy para XAUUSD, EURUSD, GBPUSD.
Convierte a CSV listo para data_loader.py
"""
import asyncio
import aiohttp
import gzip
import io
import os
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from tqdm import tqdm
import sys

# Símbolos Dukascopy (formato: PAIR)
SYMBOLS = {
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD", 
    "GBPUSD": "GBPUSD"
}

# Base URL de Dukascopy
BASE_URL = "https://datafeed.dukascopy.com/datafeed"

# Timeframes disponibles en Dukascopy (tick, 1min, 10min, 1h, 1day)
# Nos interesan: tick (para resamplear), 1h, 1day
TF_MAP = {
    "tick": "ticks",
    "1M": "m1", 
    "1H": "h1",
    "1D": "d1"
}

# Zona horaria Dukascopy = UTC
DUKASCOPY_TZ = "UTC"


async def download_month(session: aiohttp.ClientSession, symbol: str, year: int, month: int, timeframe: str = "1H") -> pd.DataFrame:
    """
    Descarga un mes de datos de Dukascopy.
    Formato URL: https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/01/15/h1_ticks.bi5
    """
    tf_path = TF_MAP.get(timeframe, "h1")
    url = f"{BASE_URL}/{symbol}/{year:04d}/{month-1:02d}/{tf_path}_ticks.bi5"
    
    try:
        async with session.get(url) as resp:
            if resp.status == 404:
                return pd.DataFrame()
            if resp.status != 200:
                print(f"  Error {resp.status}: {url}")
                return pd.DataFrame()
            
            content = await resp.read()
            
            # Dukascopy usa formato .bi5 (binario) o .csv.gz
            # Para simplificar, intentamos CSV.gz
            if content[:2] == b'\x1f\x8b':  # gzip magic
                content = gzip.decompress(content)
            
            # Parsear CSV
            try:
                df = pd.read_csv(io.BytesIO(content))
                return df
            except:
                # Formato binario .bi5 - requiere parser especial
                return parse_bi5(content)
                
    except Exception as e:
        print(f"  Error descargando {symbol} {year}-{month:02d}: {e}")
        return pd.DataFrame()


def parse_bi5(data: bytes) -> pd.DataFrame:
    """
    Parsea formato binario .bi5 de Dukascopy.
    Cada tick: 20 bytes (time, ask, bid, ask_volume, bid_volume)
    """
    # Implementación simplificada - en producción usar librería dukascopy-node o similar
    # Por ahora, retorna DataFrame vacío para indicar que necesita parser binario
    print("  Formato .bi5 detectado - requiere parser binario")
    return pd.DataFrame()


async def download_symbol_range(
    symbol: str, 
    start_year: int, 
    start_month: int, 
    end_year: int, 
    end_month: int,
    timeframe: str = "1H",
    output_dir: str = "data/raw"
) -> Path:
    """
    Descarga rango completo para un símbolo.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"{symbol}_{timeframe}_{start_year}{start_month:02d}-{end_year}{end_month:02d}.csv"
    
    all_data = []
    
    async with aiohttp.ClientSession() as session:
        current_year, current_month = start_year, start_month
        
        with tqdm(total=(end_year - start_year) * 12 + (end_month - start_month) + 1, 
                  desc=f"Descargando {symbol}") as pbar:
            while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                df = await download_month(session, symbol, current_year, current_month, timeframe)
                if not df.empty:
                    all_data.append(df)
                
                # Next month
                if current_month == 12:
                    current_month = 1
                    current_year += 1
                else:
                    current_month += 1
                
                pbar.update(1)
                await asyncio.sleep(0.1)  # Rate limiting
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        combined.to_csv(output_file, index=False)
        print(f"✅ {symbol}: {len(combined)} filas guardadas en {output_file}")
    else:
        print(f"⚠️  {symbol}: No se descargaron datos")
    
    return output_file


def download_dukascopy_csv_direct(symbol: str, year: int, month: int, day: int, timeframe: str = "1H") -> str:
    """
    Descarga directa de CSV.gz de Dukascopy para un día específico.
    URL: https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/01/15/h1_ticks.csv.gz
    """
    tf_path = TF_MAP.get(timeframe, "h1")
    url = f"{BASE_URL}/{symbol}/{year:04d}/{month-1:02d}/{day:02d}/{tf_path}_ticks.csv.gz"
    return url


async def download_daily_csv(session: aiohttp.ClientSession, url: str) -> pd.DataFrame:
    """Descarga y descomprime un CSV.gz diario."""
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return pd.DataFrame()
            content = await resp.read()
            if content[:2] == b'\x1f\x8b':
                content = gzip.decompress(content)
            df = pd.read_csv(io.BytesIO(content))
            return df
    except Exception as e:
        return pd.DataFrame()


async def download_symbol_daily(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    timeframe: str = "1H",
    output_dir: str = "data/raw"
) -> Path:
    """
    Descarga día por día usando CSV.gz (más confiable que mensual .bi5).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_path / f"{symbol}_{timeframe}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv"
    
    all_data = []
    current = start_date
    
    async with aiohttp.ClientSession() as session:
        total_days = (end_date - start_date).days + 1
        
        with tqdm(total=total_days, desc=f"Descargando {symbol} {timeframe}") as pbar:
            while current <= end_date:
                url = download_dukascopy_csv_direct(symbol, current.year, current.month, current.day, timeframe)
                df = await download_daily_csv(session, url)
                
                if not df.empty:
                    all_data.append(df)
                
                current += timedelta(days=1)
                pbar.update(1)
                await asyncio.sleep(0.05)  # Rate limit amable
    
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        # Normalizar columnas Dukascopy
        combined = normalize_dukascopy_columns(combined)
        combined.to_csv(output_file, index=False)
        print(f"✅ {symbol} {timeframe}: {len(combined)} filas → {output_file}")
    else:
        print(f"⚠️  {symbol} {timeframe}: Sin datos")
    
    return output_file


def normalize_dukascopy_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas de Dukascopy a estándar interno."""
    df = df.copy()
    
    # Columnas típicas Dukascopy: "GMT time", "Open", "High", "Low", "Close", "Volume"
    col_map = {
        "GMT time": "timestamp",
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Volume": "tick_volume"
    }
    
    df.rename(columns=col_map, inplace=True)
    
    # Asegurar timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    
    return df


async def main():
    """Descarga 2 años de datos para los 3 símbolos en 1H y 1D."""
    print("📥 Dukascopy Historical Data Downloader")
    print("=" * 50)
    
    # 2 años atrás desde hoy
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=730)  # ~2 años
    
    print(f"📅 Rango: {start_date.date()} → {end_date.date()}")
    print(f"💱 Símbolos: {list(SYMBOLS.keys())}")
    print(f"⏱️  Timeframes: 1H, 1D (base para resamplear 4H, 15M, 5M)")
    print()
    
    tasks = []
    for symbol in SYMBOLS:
        for tf in ["1H", "1D"]:
            tasks.append(download_symbol_daily(symbol, start_date, end_date, tf))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print("\n" + "=" * 50)
    print("✅ Descarga completada")
    print(f"📁 Archivos en: data/raw/")
    
    # Mostrar resumen
    for f in Path("data/raw").glob("*.csv"):
        size_mb = f.stat().st_size / (1024*1024)
        rows = sum(1 for _ in open(f)) - 1
        print(f"  {f.name}: {rows:,} filas, {size_mb:.1f} MB")


if __name__ == "__main__":
    asyncio.run(main())