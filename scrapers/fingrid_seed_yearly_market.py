import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from database import DatabaseManager
from fingrid.yearly_market_seed import seed_fingrid_yearly_market_rows


if __name__ == "__main__":
    db_path = Path(__file__).resolve().parents[1] / "data" / "aemo_data.db"
    db = DatabaseManager(str(db_path))
    result = seed_fingrid_yearly_market_rows(db)
    print(result)
