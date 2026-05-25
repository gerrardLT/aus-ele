"""Check how far back WEM dispatch solution ZIP files are available."""
import requests
import urllib3
from datetime import datetime, timedelta
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData"

# Binary search for earliest available date
# WEM new market started Oct 1, 2023 (WEMDE go-live)
# Check key dates
test_dates = [
    "20231001",  # WEMDE go-live
    "20231101",
    "20231201",
    "20240101",
    "20240301",
    "20240601",
    "20240901",
    "20241201",
    "20250101",
    "20250301",
    "20250601",
    "20260101",
    "20260301",
    "20260501",
]

print("Checking WEM dispatch solution ZIP availability:")
print("=" * 60)
for d in test_dates:
    url = f"{BASE}/previous/DispatchSolutionReference_{d}.zip"
    try:
        r = requests.head(url, verify=False, timeout=15, headers=HEADERS)
        size = r.headers.get("Content-Length", "0")
        size_mb = int(size) / 1024 / 1024 if size else 0
        status = "AVAILABLE" if r.status_code == 200 else f"HTTP {r.status_code}"
        print(f"  {d}: {status} ({size_mb:.1f} MB)" if r.status_code == 200 else f"  {d}: {status}")
    except Exception as e:
        print(f"  {d}: ERROR - {e}")

# Also check the v2 API availability (requires auth)
print("\n" + "=" * 60)
print("WEM Dispatch v2 API info:")
print("  - Requires DigiCert certificate (Market Participant only)")
print("  - Base URL: https://apis.prod.aemo.com.au:9319/WEM/v2/")
print("  - NOT publicly accessible without registration")
print("\nPublic data source (no auth required):")
print(f"  - Base URL: {BASE}/previous/")
print("  - Format: DispatchSolutionReference_YYYYMMDD.zip")
