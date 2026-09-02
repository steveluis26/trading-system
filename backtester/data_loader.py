"""
Data Loader - Carga datos históricos, resamplea timeframes, convierte zona horaria
Soporta CSV (Dukascopy, MT5 export) y Parquet.
"""
from pathlib import Path
from typing import Dict, List, Optional, Literal
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import zoneinfo


Timeframe = Literal["1D", "4H", "1H", "15M", "5M", "1M", "TICK"]


class DataLoader:
    """
    Carga datos crudos y prepara DataFrames por timeframe en zona horaria México.
    
    Expected CSV columns (Dukascopy standard):
    - timestamp (UTC), open, high, low, close, volume (tick volume), spread
    Or MT5 export: date, time, open, high, low, close, tick_volume, spread, real_volume
    """
    
    # Mapeo timeframe string -> pandas offset alias
    TF_MAP = {
        "1D": "1D",
        "4H": "4h", 
        "1H": "1h",
        "15M": "15min",
        "5M": "5min",
        "1M": "1min",
    }
    
    def __init__(self, data_dir: str = "data/raw", target_tz: str = "America/Mexico_City"):
        self.data_dir = Path(data_dir)
        self.target_tz = zoneinfo.ZoneInfo(target_tz)
        self.utc_tz = timezone.utc
    
    def load_symbol(
        self, 
        symbol: str, 
        timeframe: Timeframe = "5M",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_format: Literal["dukascopy", "mt5", "generic"] = "dukascopy"
    ) -> pd.DataFrame:
        """
        Carga un símbolo y timeframe específico.
        
        Args:
            symbol: "XAUUSD", "EURUSD", "GBPUSD"
            timeframe: Timeframe objetivo (se resamplea desde el más granular disponible)
            start_date: "YYYY-MM-DD" filtro inicio
            end_date: "YYYY-MM-DD" filtro fin
            source_format: Formato del archivo fuente
            
        Returns:
            DataFrame con columnas: timestamp (México), open, high, low, close, tick_volume
            Índice = timestamp en zona horaria México
        """
        # Buscar archivo
        file_path = self._find_file(symbol, source_format, timeframe)
        if not file_path:
            raise FileNotFoundError(f"No data file found for {symbol} {timeframe} in {self.data_dir}")
        
        # Cargar según formato
        df = self._load_file(file_path, source_format)
        
        # Normalizar columnas
        df = self._normalize_columns(df, source_format)
        
        # Convertir timestamp a UTC aware
        df = self._ensure_utc_timestamp(df)
        
        # Convertir a zona horaria México
        df = self._convert_to_target_tz(df)
        
        # Filtrar fechas si se especifica
        if start_date or end_date:
            df = self._filter_dates(df, start_date, end_date)
        
        # Resamplear al timeframe objetivo
        df = self._resample(df, timeframe)
        
        # Validar datos
        df = self._validate_data(df, symbol, timeframe)
        
        return df
    
    def load_all_timeframes(
        self, 
        symbol: str, 
        timeframes: List[Timeframe] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_format: Literal["dukascopy", "mt5", "generic"] = "dukascopy"
    ) -> Dict[Timeframe, pd.DataFrame]:
        """
        Carga todos los timeframes necesarios para el backtest.
        Carga una vez el timeframe más granular y resamplea los demás.
        """
        if timeframes is None:
            timeframes = ["1D", "4H", "1H", "15M", "5M"]
        
        # Cargar el más granular (5M o 1M si existe) - usar método interno que mantiene DatetimeIndex
        base_tf = min(timeframes, key=lambda x: self._tf_to_minutes(x))
        base_df = self._load_symbol_internal(symbol, base_tf, start_date, end_date, source_format)
        
        # Resamplear a cada timeframe
        result = {}
        for tf in timeframes:
            if tf == base_tf:
                # Convertir a formato final (timestamp como columna)
                result[tf] = self._finalize_df(base_df.copy())
            else:
                resampled = self._resample(base_df.copy(), tf, keep_index=True)
                result[tf] = self._finalize_df(resampled)
        
        return result

    def _load_symbol_internal(
        self, 
        symbol: str, 
        timeframe: Timeframe,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_format: Literal["dukascopy", "mt5", "generic"] = "dukascopy"
    ) -> pd.DataFrame:
        """Versión interna que mantiene DatetimeIndex para encadenar resamples."""
        file_path = self._find_file(symbol, source_format, timeframe)
        if not file_path:
            raise FileNotFoundError(f"No data file found for {symbol} {timeframe} in {self.data_dir}")
        
        df = self._load_file(file_path, source_format)
        df = self._normalize_columns(df, source_format)
        df = self._ensure_utc_timestamp(df)
        df = self._convert_to_target_tz(df)
        
        if start_date or end_date:
            df = self._filter_dates(df, start_date, end_date)
        
        df = self._resample(df, timeframe, keep_index=True)  # Mantiene DatetimeIndex
        df = self._validate_data(df, symbol, timeframe)
        
        return df

    def _finalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convierte DataFrame con DatetimeIndex a formato final (timestamp como columna)."""
        result = df.reset_index()
        result.rename(columns={"timestamp": "timestamp"}, inplace=True)
        return result
    
    def load_multiple_symbols(
        self,
        symbols: List[str],
        timeframes: List[Timeframe] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source_format: Literal["dukascopy", "mt5", "generic"] = "dukascopy"
    ) -> Dict[str, Dict[Timeframe, pd.DataFrame]]:
        """Carga múltiples símbolos con todos sus timeframes."""
        result = {}
        for symbol in symbols:
            result[symbol] = self.load_all_timeframes(symbol, timeframes, start_date, end_date, source_format)
        return result
    
    # ============================================================
    # Private Methods
    # ============================================================
    
    def _find_file(self, symbol: str, source_format: str, timeframe: str = None) -> Optional[Path]:
        """Busca archivo de datos para el símbolo."""
        patterns = {
            "dukascopy": [f"{symbol}*.csv", f"{symbol}*.csv.gz"],
            "mt5": [f"{symbol}*.csv", f"{symbol}*.txt"],
            "generic": [f"{symbol}*.csv", f"{symbol}*.parquet", f"{symbol}*.csv.gz"],
        }
        
        for pattern in patterns.get(source_format, patterns["generic"]):
            matches = list(self.data_dir.glob(pattern))
            if matches:
                # Si se especifica timeframe, buscar archivo que coincida
                if timeframe:
                    tf_matches = [m for m in matches if f"_{timeframe.lower()}_" in m.name.lower()]
                    if tf_matches:
                        return max(tf_matches, key=lambda p: p.stat().st_size)
                # Fallback: el más grande
                return max(matches, key=lambda p: p.stat().st_size)
        return None
    
    def _load_file(self, path: Path, source_format: str) -> pd.DataFrame:
        """Carga archivo según formato."""
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        elif path.suffix == ".gz":
            return pd.read_csv(path, compression="gzip")
        else:
            return pd.read_csv(path)
    
    def _normalize_columns(self, df: pd.DataFrame, source_format: str) -> pd.DataFrame:
        """Normaliza nombres de columnas a estándar interno."""
        df = df.copy()
        
        # Mapeos por formato
        column_maps = {
            "dukascopy": {
                "GMT time": "timestamp",
                "Open": "open", "High": "high", "Low": "low", "Close": "close",
                "Volume": "tick_volume", "Spread": "spread"
            },
            "mt5": {
                "<DATE>": "date", "<TIME>": "time",
                "<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close",
                "<TICKVOL>": "tick_volume", "<SPREAD>": "spread", "<VOL>": "real_volume"
            },
            "generic": {
                "date": "date", "time": "time", "datetime": "timestamp",
                "o": "open", "h": "high", "l": "low", "c": "close",
                "v": "tick_volume", "volume": "tick_volume"
            }
        }
        
        mapping = column_maps.get(source_format, column_maps["generic"])
        df.rename(columns=mapping, inplace=True)
        
        # Combinar date + time si existen por separado
        if "date" in df.columns and "time" in df.columns and "timestamp" not in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"])
            df.drop(columns=["date", "time"], inplace=True)
        
        # Asegurar columnas requeridas
        required = ["timestamp", "open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Columna requerida '{col}' no encontrada. Columnas: {df.columns.tolist()}")
        
        # tick_volume opcional (default 1)
        if "tick_volume" not in df.columns:
            df["tick_volume"] = 1
        
        return df[required + ["tick_volume"]]
    
    def _ensure_utc_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        """Asegura que timestamp sea UTC aware."""
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        
        # Si ya tiene timezone pero no es UTC, convertir
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert(self.utc_tz)
        else:
            # Asumir UTC si no tiene tz
            df["timestamp"] = df["timestamp"].dt.tz_localize(self.utc_tz)
        
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df
    
    def _convert_to_target_tz(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convierte índice a zona horaria objetivo (México)."""
        df = df.copy()
        df.index = df.index.tz_convert(self.target_tz)
        return df
    
    def _filter_dates(self, df: pd.DataFrame, start_date: Optional[str], end_date: Optional[str]) -> pd.DataFrame:
        """Filtra por rango de fechas en zona horaria objetivo."""
        df = df.copy()
        if start_date:
            start = pd.Timestamp(start_date, tz=self.target_tz)
            df = df[df.index >= start]
        if end_date:
            end = pd.Timestamp(end_date, tz=self.target_tz) + pd.Timedelta(days=1)
            df = df[df.index < end]
        return df
    
    def _resample(self, df: pd.DataFrame, timeframe: Timeframe, keep_index: bool = False) -> pd.DataFrame:
        """Resamplea a timeframe objetivo usando reglas OHLCV estándar."""
        if timeframe not in self.TF_MAP:
            raise ValueError(f"Timeframe no soportado: {timeframe}")
        
        rule = self.TF_MAP[timeframe]
        
        # Resample OHLC
        ohlc = df[["open", "high", "low", "close"]].resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last"
        })
        
        # Resample volume (sum)
        volume = df[["tick_volume"]].resample(rule).sum()
        
        # Combinar y dropear NaN (velas sin datos)
        result = pd.concat([ohlc, volume], axis=1).dropna()
        
        if not keep_index:
            # Reset index para tener timestamp como columna
            result = result.reset_index()
            result.rename(columns={"timestamp": "timestamp"}, inplace=True)
        
        return result
    
    def _validate_data(self, df: pd.DataFrame, symbol: str, timeframe: Timeframe) -> pd.DataFrame:
        """Validaciones básicas de calidad de datos."""
        if len(df) == 0:
            raise ValueError(f"DataFrame vacío tras cargar {symbol} {timeframe}")
        
        # Verificar gaps grandes (más de 3 velas esperadas)
        expected_freq = pd.tseries.frequencies.to_offset(self.TF_MAP[timeframe])
        # (implementación simplificada - en producción más robusta)
        
        # Verificar OHLC coherencia
        invalid = (df["high"] < df["low"]) | (df["high"] < df["open"]) | (df["high"] < df["close"]) | \
                  (df["low"] > df["open"]) | (df["low"] > df["close"])
        if invalid.any():
            print(f"WARNING: {invalid.sum()} velas con OHLC inválido en {symbol} {timeframe}")
            df = df[~invalid]
        
        return df
    
    def _tf_to_minutes(self, tf: Timeframe) -> int:
        """Convierte timeframe a minutos para ordenar."""
        mapping = {"1D": 1440, "4H": 240, "1H": 60, "15M": 15, "5M": 5, "1M": 1}
        return mapping.get(tf, 9999)


# Función de conveniencia
def load_backtest_data(
    symbols: List[str],
    data_dir: str = "data/raw",
    start_date: str = None,
    end_date: str = None
) -> Dict[str, Dict[Timeframe, pd.DataFrame]]:
    """Carga lista de símbolos con todos los timeframes estándar."""
    loader = DataLoader(data_dir)
    return loader.load_multiple_symbols(symbols, start_date=start_date, end_date=end_date)