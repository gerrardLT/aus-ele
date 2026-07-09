import argparse
import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from database import DatabaseManager
from fingrid.importer import import_fingrid_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import real Fingrid CSV data into PostgreSQL")
    parser.add_argument("--dataset", required=True, help="Fingrid dataset id, for example 317")
    parser.add_argument("--input", required=True, help="Path to exported Fingrid CSV file")
    parser.add_argument("--value-column", help="Optional explicit value column name")
    parser.add_argument("--delimiter", help="Optional CSV delimiter override")
    args = parser.parse_args()

    db = DatabaseManager()
    result = import_fingrid_csv(
        db,
        dataset_id=args.dataset,
        csv_path=args.input,
        value_column=args.value_column,
        delimiter=args.delimiter,
    )
    print(result)
