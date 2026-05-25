"""Quick check of WEM dispatch solution file sizes."""
import requests
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData"

# Check recent dates
dates = ["20260518", "20260517", "20260516", "20260515"]
for d in dates:
    url = f"{BASE}/previous/DispatchSolutionReference_{d}.zip"
    try:
        r = requests.head(url, verify=False, timeout=30, headers=HEADERS)
        size = r.headers.get("Content-Length", "unknown")
        if size != "unknown":
            size_mb = int(size) / 1024 / 1024
            print(f"{d}: {r.status_code} - {size_mb:.1f} MB")
        else:
            print(f"{d}: {r.status_code} - size unknown")
    except Exception as e:
        print(f"{d}: ERROR - {e}")

# Check current day JSON listing
print("\nCurrent day JSON files:")
try:
    r = requests.get(f"{BASE}/current/", verify=False, timeout=30, headers=HEADERS)
    import re
    jsons = re.findall(r"ReferenceDispatchSolution_\d+\.json", r.text)
    print(f"  Found {len(jsons)} JSON files for today")
    if jsons:
        # Check size of one JSON
        sample_url = f"{BASE}/current/{jsons[0]}"
        r2 = requests.head(sample_url, verify=False, timeout=30, headers=HEADERS)
        json_size = r2.headers.get("Content-Length", "unknown")
        if json_size != "unknown":
            print(f"  Single JSON size: {int(json_size)/1024:.1f} KB")
        print(f"  Estimated daily total: {len(jsons)} files x ~{int(json_size or 0)/1024:.0f} KB = ~{len(jsons) * int(json_size or 0) / 1024 / 1024:.1f} MB uncompressed")
except Exception as e:
    print(f"  ERROR: {e}")
