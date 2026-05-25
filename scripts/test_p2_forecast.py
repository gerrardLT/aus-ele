import requests
r = requests.get("http://127.0.0.1:8085/api/p2/forecast-layer?market=NEM&region=NSW1&horizon=24h")
d = r.json()
print(f"Status: {r.status_code}")
print(f"windows count: {len(d.get('windows', []))}")
print(f"coverage: {d.get('coverage', {})}")
if d.get('windows'):
    print(f"First window: {d['windows'][0]}")
else:
    print("NO WINDOWS - this is why GridForecast shows empty")
    print(f"Keys in response: {list(d.keys())}")
