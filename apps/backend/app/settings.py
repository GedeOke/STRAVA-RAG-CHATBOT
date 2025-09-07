import os
from dotenv import load_dotenv

load_dotenv()

# DB (sudah ada di kamu)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://dev:dev@localhost:5432/strava_rag")

# STRAVA
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/callback")

# token awal (nanti bisa di-refresh otomatis)
STRAVA_ACCESS_TOKEN = os.getenv("STRAVA_ACCESS_TOKEN", "")
STRAVA_REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN", "")

# optional: default club id buat cepat coba
DEFAULT_CLUB_ID = os.getenv("DEFAULT_CLUB_ID")
