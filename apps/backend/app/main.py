from fastapi import FastAPI
from .routers import strava as strava_router
from .db import engine, Base   

app = FastAPI(title="Strava RAG API - Data Fetch")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

app.include_router(strava_router.router, prefix="/strava", tags=["strava"])

@app.get("/health")
def health():
    return {"ok": True}
