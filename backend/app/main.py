from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health_router, strava_router

app = FastAPI(title="Strava RAG Chatbot API")

# CORS (development-friendly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # allow any origin (frontend dev, file://, live server)
    allow_credentials=False,       # must be False when using wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)

# Extra safety: always append CORS headers
@app.middleware("http")
async def add_cors_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("Access-Control-Allow-Headers", "*")
    return response

# daftarkan router
app.include_router(health_router.router)
app.include_router(strava_router.router)
