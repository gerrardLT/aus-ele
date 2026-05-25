"""Check earliest available WEM data on the public server."""
import requests
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://data.wa.aemo.com.au/public/market-data/wemde"

# Test dates before WEMDE go-live (Oct 1, 2023)
# WEM existed before WEMDE but used a different system (STEM/balancing market)
# Check if older dispatch data exists
print("Checking WEM data availability before WEMDE go-live (2023-10-01):")
print("=" * 60)

# Dispatch Solution (new WEMDE format)
print("\n1. Dispatch Solution (WEMDE format):")
for d in ["20230901", "20230915", "20230930", "20231001", "20231002"]:
    url = f"{BASE}/dispatchSolution/dispatchData/previous/DispatchSolutionReference_{d}.zip"
    try:
        r = requests.head(url, verify=False, timeout=15, headers=HEADERS)
        size = int(r.headers.get("Content-Length", "0")) / 1024 / 1024
        print(f"  {d}: {'AVAILABLE' if r.status_code == 200 else f'HTTP {r.status_code}'} ({size:.1f} MB)" if r.status_code == 200 else f"  {d}: HTTP {r.status_code}")
    except Exception as e:
        print(f"  {d}: ERROR - {e}")

# RTP (new WEMDE format)
print("\n2. Reference Trading Price (WEMDE format):")
for d in ["20230901", "20230915", "20230930", "20231001", "20231002"]:
    url = f"{BASE}/referenceTradingPrice/previous/ReferenceTradingPrice_{d}.zip"
    try:
        r = requests.head(url, verify=False, timeout=15, headers=HEADERS)
        size = int(r.headers.get("Content-Length", "0")) / 1024
        print(f"  {d}: {'AVAILABLE' if r.status_code == 200 else f'HTTP {r.status_code}'} ({size:.1f} KB)" if r.status_code == 200 else f"  {d}: HTTP {r.status_code}")
    except Exception as e:
        print(f"  {d}: ERROR - {e}")

# Check old WEM data format (pre-WEMDE, balancing market)
print("\n3. Old WEM format (pre-WEMDE balancing market):")
old_base = "https://data.wa.aemo.com.au/public/market-data/wem"
old_paths = [
    "/facility-scada/previous/",
    "/balancing/previous/",
    "/stem/previous/",
]
for path in old_paths:
    url = old_base + path
    try:
        r = requests.get(url, verify=False, timeout=15, headers=HEADERS)
        if r.status_code == 200:
            # Count files in listing
            import re
            files = re.findall(r'href="([^"]+\.(zip|csv))"', r.text, re.IGNORECASE)
            print(f"  {path}: AVAILABLE ({len(files)} files found)")
            if files:
                print(f"    Sample: {files[0][0]}")
        else:
            print(f"  {path}: HTTP {r.status_code}")
    except Exception as e:
        print(f"  {path}: ERROR - {e}")

print("\n" + "=" * 60)
print("Summary:")
print("  - WEMDE (new market design) data starts: 2023-10-01")
print("  - Old WEM (balancing/STEM) data may exist in different paths")
print("  - The two formats are incompatible (different market design)")
