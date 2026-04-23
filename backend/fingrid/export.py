import csv
import io


def build_fingrid_csv(series: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["timestamp", "timestamp_utc", "value", "unit"])
    writer.writeheader()
    for row in series:
        writer.writerow(
            {
                "timestamp": row["timestamp"],
                "timestamp_utc": row["timestamp_utc"],
                "value": row["value"],
                "unit": row["unit"],
            }
        )
    return buffer.getvalue()
