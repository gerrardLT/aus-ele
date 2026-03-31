import requests
import zipfile
import io

url = "http://www.nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/2014/MMSDM_2014_05.zip"
print(f"Downloading {url}...")
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
resp = requests.get(url, stream=True, headers=headers)
if resp.status_code == 200:
    content = resp.content
    print(f"Downloaded {len(content)} bytes")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
        print("Files inside top zip:")
        for n in names[:10]:
            print(n)
        
        # specifically look for tradingprice
        for fname in names:
            if "TRADINGPRICE" in fname.upper():
                print(f"FOUND TRADINGPRICE: {fname}")
else:
    print(f"Failed: {resp.status_code}")
