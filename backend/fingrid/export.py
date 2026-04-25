import csv
import io


def build_fingrid_csv(series: list[dict]) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "timestamp",
        "timestamp_utc",
        "bucket_start",
        "bucket_end",
        "value",
        "avg_value",
        "peak_value",
        "trough_value",
        "sample_count",
        "unit",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in series:
        writer.writerow({key: row.get(key) for key in fieldnames})
    return buffer.getvalue()
