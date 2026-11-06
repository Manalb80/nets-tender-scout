"""Quick API test."""
import json
import urllib.request

BASE = "http://127.0.0.1:8766"

for endpoint in ["/api/health", "/api/tenders", "/api/scans", "/api/proposals", "/api/solutions"]:
    try:
        resp = urllib.request.urlopen(BASE + endpoint)
        data = json.loads(resp.read())
        if isinstance(data, list):
            print(f"  {endpoint:25s} -> {len(data)} items")
        else:
            print(f"  {endpoint:25s} -> {data}")
    except Exception as e:
        print(f"  {endpoint:25s} -> ERROR: {e}")

# Test frontend
try:
    resp = urllib.request.urlopen(BASE + "/")
    html = resp.read().decode()
    print(f"\n  Frontend: {len(html)} bytes, {'NETS Tender Scout' if 'Tender Scout' in html else 'MISSING TITLE'}")
except Exception as e:
    print(f"\n  Frontend: ERROR: {e}")

print("\nAll endpoints tested.")
