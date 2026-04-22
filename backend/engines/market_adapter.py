from typing import List, Dict, Optional
import sqlite3

class MarketAdapter:
    def __init__(self, db_connection: sqlite3.Connection):
        self.conn = db_connection

    def fetch_historical_data(
        self, 
        region: str, 
        year: int, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetches unified market data regardless of whether it's NEM or WEM.
        Normalizes column names and time intervals to a common format.
        """
        if region == "WEM":
            return self._fetch_wem_data(year, start_date, end_date)
        else:
            return self._fetch_nem_data(region, year, start_date, end_date)

    def _fetch_nem_data(self, region: str, year: int, start_date: str, end_date: str) -> List[Dict]:
        table_name = f"trading_price_{year}"
        cursor = self.conn.cursor()
        
        # Check if table exists
        cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            return []

        query = f"""
            SELECT 
                settlement_date as interval_time,
                rrp as energy_price,
                raise6sec_rrp as fcas_raise_6sec,
                raise60sec_rrp as fcas_raise_60sec,
                raise5min_rrp as fcas_raise_5min,
                raisereg_rrp as fcas_raise_reg,
                lower6sec_rrp as fcas_lower_6sec,
                lower60sec_rrp as fcas_lower_60sec,
                lower5min_rrp as fcas_lower_5min,
                lowerreg_rrp as fcas_lower_reg
            FROM {table_name}
            WHERE region_id = ?
        """
        params = [region]
        
        if start_date:
            query += " AND settlement_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND settlement_date <= ?"
            params.append(end_date)
            
        query += " ORDER BY settlement_date ASC"
        
        cursor.execute(query, tuple(params))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _fetch_wem_data(self, year: int, start_date: str, end_date: str) -> List[Dict]:
        # WEM implementation (placeholder for future full integration)
        # Would fetch from wem_trading_price and wem_ess_price, join them,
        # and interpolate/downsample to match the standard 5-minute or 30-minute blocks.
        return []
