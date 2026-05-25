import sys
sys.path.insert(0, "backend")
from grid_forecast import NEM_PREDISPATCH_LISTING_URL, _extract_listing_links, _parse_predispatch_csv_bytes, HEADERS
import requests, zipfile, io
from urllib.parse import urljoin

r = requests.get(NEM_PREDISPATCH_LISTING_URL, headers=HEADERS, timeout=20)
links = _extract_listing_links(r.text)
latest_url = urljoin(NEM_PREDISPATCH_LISTING_URL, links[-1])
file_res = requests.get(latest_url, headers=HEADERS, timeout=30)

with zipfile.ZipFile(io.BytesIO(file_res.content)) as zf:
    for name in zf.namelist():
        if not name.lower().endswith(".csv"):
            continue
        raw = zf.open(name).read()
        text = raw.decode("utf-8-sig")
        lines = text.splitlines()
        
        # Find lines with REGIONID
        region_lines = [l for l in lines if "REGIONID" in l.upper() and ("RRP" in l.upper() or "PRICE" in l.upper())]
        print(f"Lines with REGIONID + RRP/PRICE: {len(region_lines)}")
        if region_lines:
            print(f"First match: {region_lines[0][:200]}")
        
        # Find REGION_SOLUTION section
        region_sol = [l for l in lines if "REGION_SOLUTION" in l.upper()]
        print(f"\nLines with REGION_SOLUTION: {len(region_sol)}")
        if region_sol:
            # Find the I (header) line
            headers = [l for l in region_sol if l.startswith("I,")]
            if headers:
                print(f"Header: {headers[0][:200]}")
            # Find first D (data) line
            data_lines = [l for l in region_sol if l.startswith("D,")]
            if data_lines:
                print(f"First data: {data_lines[0][:200]}")
                print(f"Data lines count: {len(data_lines)}")
        
        # Test the parser
        result = _parse_predispatch_csv_bytes(raw, "NSW1")
        print(f"\nParser result for NSW1: {len(result)} records")
        if result:
            print(f"First: {result[0]}")
        break
