# scripts/test_activity_detail.py
import os
import sys
import requests
from dotenv import load_dotenv

# load env dari infra/env/.backend.env
load_dotenv("infra/env/.backend.env")

ACCESS_TOKEN = os.getenv("STRAVA_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    print("❌ STRAVA_ACCESS_TOKEN tidak ketemu. Cek infra/env/.backend.env")
    sys.exit(1)

if len(sys.argv) < 2:
    print("⚡ Usage: python scripts/test_activity_detail.py ACTIVITY_ID")
    sys.exit(1)

ACTIVITY_ID = sys.argv[1]

url = f"https://www.strava.com/api/v3/activities/{ACTIVITY_ID}"
headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

print(f"👉 Fetching activity {ACTIVITY_ID} ...")
res = requests.get(url, headers=headers)

print("Status:", res.status_code)
try:
    data = res.json()
    # tampilkan sebagian penting aja
    print("start_date:", data.get("start_date"))
    print("start_date_local:", data.get("start_date_local"))
    print("name:", data.get("name"))
    print("distance:", data.get("distance"))
    print("moving_time:", data.get("moving_time"))
except Exception as e:
    print("❌ Gagal parse response:", e)
    print(res.text)
