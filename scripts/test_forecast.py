import requests
r = requests.get("http://127.0.0.1:8085/api/grid-forecast?market=NEM&region=NSW1&horizon=24h")
d = r.json()
print(f"forward_points: {d.get('forward_points', 0)}")
print(f"sources_used: {d.get('metadata', {}).get('sources_used', [])}")
print(f"warnings: {d.get('metadata', {}).get('warnings', [])}")
print(f"forecast_mode: {d.get('metadata', {}).get('forecast_mode', '')}")
fwd = d.get("forward", [])
print(f"forward data count: {len(fwd)}")
if fwd:
    print(f"first: {fwd[0]}")
