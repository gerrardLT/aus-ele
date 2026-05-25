import sys
sys.path.insert(0, "backend")
from grid_forecast import NEM_PREDISPATCH_LISTING_URL, _extract_listing_links, HEADERS
import requests
from urllib.parse import urljoin

# Fetch listing
r = requests.get(NEM_PREDISPATCH_LISTING_URL, headers=HEADERS, timeout=20)
print(f"Listing status: {r.status_code}")
links = _extract_listing_links(r.text)
print(f"Found {len(links)} links")
if links:
    print(f"Last 3: {links[-3:]}")
    # Fetch latest file
    latest_url = urljoin(NEM_PREDISPATCH_LISTING_URL, links[-1])
    print(f"Fetching: {latest_url}")
    file_res = requests.get(latest_url, headers=HEADERS, timeout=30)
    print(f"File status: {file_res.status_code}, size: {len(file_res.content)} bytes")
    
    # Try to parse
    import zipfile, io, csv
    content = file_res.content
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist()[:3]:
                print(f"  ZIP member: {name}")
                with zf.open(name) as f:
                    lines = f.read().decode("utf-8-sig").splitlines()
                    print(f"  Lines: {len(lines)}")
                    # Print first 5 lines
                    for line in lines[:5]:
                        print(f"    {line[:150]}")
    else:
        text = content.decode("utf-8-sig")
        lines = text.splitlines()
        print(f"CSV lines: {len(lines)}")
        for line in lines[:5]:
            print(f"  {line[:150]}")
