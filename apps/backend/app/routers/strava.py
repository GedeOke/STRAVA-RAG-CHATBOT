from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.strava import client, ingest, retriever
from ..services.strava import answerer  # pastikan file answerer.py ada

router = APIRouter(tags=["strava"])

@router.get("/me")
def get_me():
    return client.me()

@router.get("/clubs/{club_id}/activities")
def get_club_feed(club_id: int, page: int = 1, per_page: int = 50):
    """Feed aktivitas club (ringkas, recent)."""
    return client.club_activities(club_id, page=page, per_page=per_page)

@router.post("/clubs/{club_id}/ingest")
def ingest_club(club_id: int, db: Session = Depends(get_db)):
    """Tarik feed club → simpan ke DB + (opsional) buat summary di utils kalau dipakai."""
    try:
        return ingest.ingest_club_feed(db, club_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
def search(query: str, top_k: int = 5, db: Session = Depends(get_db)):
    """Semantic search (pgvector + cross-encoder)."""
    try:
        return retriever.search_similar(db, query, top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qa")
def qa(query: str, top_k: int = 50, db: Session = Depends(get_db)):
    """Jawaban berbasis RAG (retriever -> LLM)."""
    try:
        return answerer.answer(db, query, top_k=top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))