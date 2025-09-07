from fastapi import APIRouter, Query, Depends
from typing import Optional
from ..services.strava import client
from ..settings import DEFAULT_CLUB_ID
from sqlalchemy.orm import Session
from ..db import get_db
from ..services.strava import client, ingest
from ..services.strava import embedding_job
from app.services.strava import summary_job

# router = APIRouter()
router = APIRouter(prefix="/strava", tags=["strava"])

@router.get("/me")
def get_me():
    return client.me()

@router.get("/clubs/{club_id}/activities")
def get_club_feed(club_id: int, page: int = 1, per_page: int = 50):
    """Feed aktivitas club (ringkas, recent)."""
    return client.club_activities(club_id, page=page, per_page=per_page)

@router.post("/clubs/{club_id}/ingest")
def ingest_club(club_id: int, db: Session = Depends(get_db)):
    """Tarik feed club → simpan ke DB + bikin summary"""
    return ingest.ingest_club_feed(db, club_id)

@router.post("/summaries/generate")
def generate_summaries(limit: int = 50, db: Session = Depends(get_db)):
    return summary_job.generate_summaries(db, limit=limit)

@router.post("/embeddings/generate")
def generate_embeddings(limit: int = 50, db: Session = Depends(get_db)):
    try:
        return embedding_job.generate_embeddings(db, limit=limit)
    except Exception as e:
        import traceback
        traceback.print_exc()   # tampil di docker logs
        return {"error": str(e)}  # tampil di Swagger response


# @router.get("/activities/{activity_id}")
# def get_activity_detail(activity_id: int):
#     """Detail satu aktivitas (lebih lengkap dari feed)."""
#     return client.activity_detail(activity_id)

# @router.get("/activities/{activity_id}/streams")
# def get_activity_streams(activity_id: int,
#                          keys: str = Query("time,heartrate,latlng,velocity_smooth,cadence,watts")):
#     """Time-series (jika izin & data tersedia)."""
#     return client.activity_streams(activity_id, keys=keys)

# @router.get("/clubs/{club_id}/activities/full")
# def get_club_full(club_id: int,
#                   pages: int = 2,
#                   per_page: int = 50,
#                   include_streams: bool = False):
#     """
#     Ambil feed club, lalu untuk setiap item ambil detail (+opsional streams).
#     Hati-hati quota & privasi — idealnya semua member authorize app kamu.
#     """
#     return client.club_activities_full(club_id, pages=pages, per_page=per_page,
#                                        include_streams=include_streams)

# @router.get("/club/default/full")
# def get_default_club_full(pages: int = 2, per_page: int = 50, include_streams: bool = False):
#     if not DEFAULT_CLUB_ID:
#         return {"error": "DEFAULT_CLUB_ID not set in env"}
#     return client.club_activities_full(int(DEFAULT_CLUB_ID), pages=pages, per_page=per_page,
#                                        include_streams=include_streams)
