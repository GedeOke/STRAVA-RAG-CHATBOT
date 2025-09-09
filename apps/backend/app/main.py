from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import strava as strava_router
from .db import engine, Base

app = FastAPI(title="Strava RAG API - Data Fetch")

app.add_middleware(
    CORSMiddleware,
    # izinkan localhost & 127.0.0.1 di semua port (termasuk 5500)
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

app.include_router(strava_router.router, prefix="/strava", tags=["strava"])

@app.get("/health")
def health():
    return {"ok": True}
