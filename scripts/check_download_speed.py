"""Quick bandwidth test: download a small portion of one WEM ZIP to estimate speed."""
import time
import requests
import urllib3
urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0"}
URL = "https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData/previous/DispatchSolutionReference_20260517.zip"

# Download first 5 MB to estimate speed
CHUNK_SIZE = 256 * 1024
TARGET_BYTES = 5 * 1024 * 1024  # 5 MB

print("Testing download speed from data.wa.aemo.com.au...")
print(f"Downloading first {TARGET_BYTES / 1024 / 1024:.0f} MB of a WEM ZIP file...")

start = time.time()
downloaded = 0

try:
    r = requests.get(URL, headers=HEADERS, verify=False, timeout=60, stream=True)
    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
        downloaded += len(chunk)
        if downloaded >= TARGET_BYTES:
            break
    r.close()
except Exception as e:
    print(f"Error: {e}")

elapsed = time.time() - start
speed_mbps = (downloaded / 1024 / 1024) / elapsed

print(f"\nResults:")
print(f"  Downloaded: {downloaded / 1024 / 1024:.1f} MB")
print(f"  Time: {elapsed:.1f} seconds")
print(f"  Speed: {speed_mbps:.2f} MB/s ({speed_mbps * 8:.1f} Mbps)")

# Estimate for 30 days
daily_size_mb = 285
total_30_days_mb = daily_size_mb * 30
estimated_seconds = total_30_days_mb / speed_mbps
estimated_minutes = estimated_seconds / 60

print(f"\n30-day estimate:")
print(f"  Total download: {total_30_days_mb / 1024:.1f} GB")
print(f"  Estimated time: {estimated_minutes:.0f} minutes ({estimated_minutes / 60:.1f} hours)")
print(f"  (Plus ~1s sleep between days = +30s)")

# 7-day estimate
total_7_days_mb = daily_size_mb * 7
estimated_7_seconds = total_7_days_mb / speed_mbps
print(f"\n7-day estimate:")
print(f"  Total download: {total_7_days_mb / 1024:.1f} GB")
print(f"  Estimated time: {estimated_7_seconds / 60:.0f} minutes")
