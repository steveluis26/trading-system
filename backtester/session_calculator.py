"""
Session Calculator - Calcula High/Low de sesiones (Asia, Londres, NY) en zona horaria México
Detecta zonas de confluencia (fractal) donde 2-3 sesiones coinciden.
"""
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import zoneinfo
from backtester.models import SessionLevel, SessionLevels, ConfluenceZone, SessionName
from backtester.config_loader import get_sessions


class SessionCalculator:
    """
    Calcula niveles de sesión y zonas de confluencia.
    
    Sesiones en hora México (America/Mexico_City):
    - ASIA: 18:00-03:00 (cruza medianoche, día = día de cierre 03:00)
    - LONDON: 02:00-11:00
    - NEWYORK: 07:00-16:00
    """
    
    def __init__(self, sessions_config=None):
        self.config = sessions_config or get_sessions()
        self.tz = zoneinfo.ZoneInfo(self.config.timezone)
        self.sessions_def = self.config.sessions
        self.tolerance_pips = self.config.confluence_tolerance_pips
    
    def calculate_daily_levels(
        self, 
        candles_5m: pd.DataFrame, 
        date: datetime
    ) -> SessionLevels:
        """
        Calcula High/Low de las 3 sesiones para una fecha dada.
        
        Args:
            candles_5m: DataFrame con columnas [timestamp, open, high, low, close, tick_volume]
                       timestamp en zona horaria México (America/Mexico_City)
            date: Fecha para la que calcular (día de cierre de sesión Asia = día D)
            
        Returns:
            SessionLevels con high/low de cada sesión
        """
        mexico_tz = self.tz
        
        # Asegurar que timestamp es el índice y está en zona horaria México
        df = candles_5m.copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize(mexico_tz)
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert(mexico_tz)
            df.set_index("timestamp", inplace=True)
        elif df.index.tz is None:
            df.index = df.index.tz_localize(mexico_tz)
        else:
            df.index = df.index.tz_convert(mexico_tz)
        
        df.sort_index(inplace=True)
        
        # Definir rangos de sesión para la fecha objetivo
        # ASIA: D-1 18:00 → D 03:00 (día D = día de cierre)
        asia_start = pd.Timestamp(date - timedelta(days=1), tz=mexico_tz).replace(hour=18, minute=0, second=0, microsecond=0)
        asia_end = pd.Timestamp(date, tz=mexico_tz).replace(hour=3, minute=0, second=0, microsecond=0)
        
        # LONDON: D 02:00 → D 11:00
        london_start = pd.Timestamp(date, tz=mexico_tz).replace(hour=2, minute=0, second=0, microsecond=0)
        london_end = pd.Timestamp(date, tz=mexico_tz).replace(hour=11, minute=0, second=0, microsecond=0)
        
        # NEWYORK: D 07:00 → D 16:00
        ny_start = pd.Timestamp(date, tz=mexico_tz).replace(hour=7, minute=0, second=0, microsecond=0)
        ny_end = pd.Timestamp(date, tz=mexico_tz).replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Filtrar velas por sesión
        asia_candles = df[(df.index >= asia_start) & (df.index < asia_end)]
        london_candles = df[(df.index >= london_start) & (df.index < london_end)]
        ny_candles = df[(df.index >= ny_start) & (df.index < ny_end)]
        
        # Crear SessionLevel objects
        def make_level(sess_name: SessionName, candles: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> SessionLevel:
            if len(candles) == 0:
                return SessionLevel(
                    session=sess_name,
                    high=None, low=None,
                    start_time=start, end_time=end,
                    candle_count=0
                )
            return SessionLevel(
                session=sess_name,
                high=float(candles["high"].max()),
                low=float(candles["low"].min()),
                start_time=start, end_time=end,
                candle_count=len(candles)
            )
        
        asia_level = make_level(SessionName.ASIA, asia_candles, asia_start, asia_end)
        london_level = make_level(SessionName.LONDON, london_candles, london_start, london_end)
        ny_level = make_level(SessionName.NEWYORK, ny_candles, ny_start, ny_end)
        
        return SessionLevels(
            date=pd.Timestamp(date, tz=mexico_tz).replace(hour=0, minute=0, second=0, microsecond=0),
            asia=asia_level,
            london=london_level,
            newyork=ny_level,
            timezone=str(mexico_tz)
        )
    
    def calculate_levels_range(
        self, 
        candles_5m: pd.DataFrame, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[datetime, SessionLevels]:
        """
        Calcula niveles para un rango de fechas.
        Retorna dict {date: SessionLevels}.
        """
        result = {}
        current = start_date
        while current <= end_date:
            try:
                levels = self.calculate_daily_levels(candles_5m, current)
                result[current] = levels
            except Exception as e:
                print(f"Warning: No se pudieron calcular niveles para {current.date()}: {e}")
            current += timedelta(days=1)
        return result
    
    def detect_confluence_zones(
        self, 
        session_levels: SessionLevels, 
        symbol: str = "XAUUSD"
    ) -> List[ConfluenceZone]:
        """
        Detecta zonas donde 2-3 sesiones coinciden en precio (±tolerancia).
        
        Args:
            session_levels: SessionLevels del día
            symbol: Símbolo para obtener tolerancia en pips
            
        Returns:
            Lista de ConfluenceZone ordenadas por strength (3 > 2)
        """
        tolerance = self.tolerance_pips.get(symbol, 10)  # pips
        pip_size = 0.01 if "XAU" in symbol else 0.0001
        tolerance_price = tolerance * pip_size
        
        # Recopilar todos los niveles válidos
        all_levels = []
        for sess_name, sess in [
            (SessionName.ASIA, session_levels.asia),
            (SessionName.LONDON, session_levels.london),
            (SessionName.NEWYORK, session_levels.newyork)
        ]:
            if sess.high is not None:
                all_levels.append(("HIGH", sess_name, sess.high))
            if sess.low is not None:
                all_levels.append(("LOW", sess_name, sess.low))
        
        if len(all_levels) < 2:
            return []
        
        # Agrupar niveles cercanos
        zones = []
        used = set()
        
        for i, (type1, sess1, price1) in enumerate(all_levels):
            if i in used:
                continue
            
            coinciding = [(type1, sess1, price1)]
            used.add(i)
            
            for j, (type2, sess2, price2) in enumerate(all_levels):
                if j in used or j <= i:
                    continue
                if sess1 != sess2 and abs(price1 - price2) <= tolerance_price:
                    coinciding.append((type2, sess2, price2))
                    used.add(j)
            
            if len(coinciding) >= 2:
                avg_price = sum(p for _, _, p in coinciding) / len(coinciding)
                zones.append(ConfluenceZone(
                    price=avg_price,
                    sessions=[s for _, s, _ in coinciding],
                    types=[t for t, _, _ in coinciding],
                    strength=len(coinciding),
                    is_high=all(t == "HIGH" for t, _, _ in coinciding),
                    is_low=all(t == "LOW" for t, _, _ in coinciding),
                    tolerance_pips=tolerance
                ))
        
        # Ordenar: strength 3 primero, luego 2, luego por precio
        zones.sort(key=lambda z: (-z.strength, z.price))
        return zones
    
    def get_key_level_for_trend(
        self, 
        session_levels: SessionLevels, 
        trend: str
    ) -> Optional[float]:
        """
        Obtiene el nivel clave según la tendencia macro.
        BULLISH → busca soporte (LOW confluente)
        BEARISH → busca resistencia (HIGH confluente)
        """
        zones = self.detect_confluence_zones(session_levels)
        
        if trend == "BULLISH":
            # Buscar zona de soporte (LOW) más relevante
            low_zones = [z for z in zones if z.is_low]
            if low_zones:
                return low_zones[0].price  # La más fuerte (strength 3 > 2)
            # Fallback: Low de sesión individual más reciente
            for sess in [session_levels.london, session_levels.newyork, session_levels.asia]:
                if sess.low is not None:
                    return sess.low
        elif trend == "BEARISH":
            # Buscar zona de resistencia (HIGH) más relevante
            high_zones = [z for z in zones if z.is_high]
            if high_zones:
                return high_zones[0].price
            for sess in [session_levels.london, session_levels.newyork, session_levels.asia]:
                if sess.high is not None:
                    return sess.high
        
        return None


# Función de conveniencia
def calculate_session_levels_for_backtest(
    candles_5m: pd.DataFrame,
    start_date: str,
    end_date: str,
    symbol: str = "XAUUSD"
) -> Dict[datetime, Tuple[SessionLevels, List[ConfluenceZone]]]:
    """
    Calcula niveles y confluencias para todo el rango de backtest.
    Retorna {date: (SessionLevels, [ConfluenceZone])}.
    """
    calc = SessionCalculator()
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    
    result = {}
    current = datetime.combine(start, time(0, 0))
    end_dt = datetime.combine(end, time(0, 0))
    
    while current <= end_dt:
        levels = calc.calculate_daily_levels(candles_5m, current)
        zones = calc.detect_confluence_zones(levels, symbol)
        result[current] = (levels, zones)
        current += timedelta(days=1)
    
    return result