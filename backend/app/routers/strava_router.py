from fastapi import APIRouter, Query
from app.core.logger import logger
from app.core.utils import timer, now_str
from app.services.gsheet.sync import sync_gsheet_to_chroma
from app.services.rag.retriever import retrieve_context
from app.services.chroma.db_client import get_collection
from app.core.config import settings
from app.services.rag.pipeline import rag_answer
from app.core.memory import get_session, update_session
from typing import Optional, Dict, Any, List
from datetime import datetime, date
import re


router = APIRouter(prefix="/strava", tags=["Strava Club"])


# ==================================================
# Refresh Data dari Google Sheet -> ChromaDB
# ==================================================
@router.post("/refresh")
@timer
def refresh_data():
    """
    Sinkronisasi ulang data dari Google Sheet ke ChromaDB.
    - Hanya update entitas (member) yang berubah.
    - Log semua perubahan di logger.
    """
    try:
        logger.info("Memulai sinkronisasi data dari Google Sheet...")
        result = sync_gsheet_to_chroma()
        if result and result.get("status") == "error":
            # propagasikan error dari fungsi sync
            logger.error(f"Gagal sinkronisasi: {result.get('message')}")
            return {"status": "error", "message": result.get("message"), "time": now_str()}

        updated = result.get("updated", 0)
        skipped = result.get("skipped", 0)
        logger.info(
            f"Sinkronisasi selesai - updated: {updated} | skipped: {skipped}"
        )
        return {
            "status": "ok",
            "updated": updated,
            "skipped": skipped,
            "time": now_str(),
        }
    except Exception as e:
        logger.exception(f"Gagal sinkronisasi: {e}")
        return {"status": "error", "message": str(e), "time": now_str()}


# ==================================================
# Ask / Query ke Chroma (Retriever)
# ==================================================
@router.get("/ask")
@timer
def ask(
    query: str = Query(..., description="Pertanyaan user"),
    with_answer: bool = Query(False, description="Jika true, jalankan pipeline RAG penuh"),
    member: str = Query(None, description="Nama member spesifik (opsional)"),
    month: int = Query(None, ge=1, le=12, description="Bulan (1-12), opsional"),
    year: int = Query(None, ge=2000, le=2100, description="Tahun (YYYY), opsional"),
    top_k: int = Query(5, ge=1, le=20, description="Jumlah konteks yang diambil"),
    session_id: str = Query(None, description="ID sesi percakapan untuk memory"),
):
    try:
        # Read memory and backfill missing filters
        sess = get_session(session_id)
        eff_member = member or sess.get("member")
        eff_month = month or sess.get("month")
        eff_year = year or sess.get("year")

        if with_answer:
            result = rag_answer(query, top_k=top_k, member=eff_member, month=eff_month, year=eff_year, session_id=session_id)
            result["time"] = now_str()
            return result
        else:
            contexts = retrieve_context(query, top_k=top_k, member=eff_member)
            # memory: update last query
            update_session(session_id, last_query=query)
            return {
                "status": "ok" if contexts else "not_found",
                "query": query,
                "contexts": contexts,
                "filters": {"member": eff_member, "month": eff_month, "year": eff_year},
                "time": now_str(),
            }
    except Exception as e:
        logger.exception(f"/ask error: {e}")
        return {"status": "error", "message": str(e), "time": now_str()}


# ==================================================
# Status ChromaDB
# ==================================================
@router.get("/status")
def chroma_status():
    """
    Menampilkan status koleksi ChromaDB (jumlah dokumen dan konfigurasi dasar).
    """
    try:
        collection = get_collection()
        count = collection.count()
        logger.info(f"Status koleksi: {count} dokumen tersimpan.")
        return {
            "status": "ok",
            "collection": settings.CHROMA_COLLECTION,
            "total_documents": count,
            "time": now_str(),
        }
    except Exception as e:
        logger.exception(f"Gagal membaca status ChromaDB: {e}")
        return {"status": "error", "message": str(e), "time": now_str()}


# ==================================================
# Leaderboard (week / month / year)
# ==================================================
@router.get("/leaderboard")
def leaderboard(
    scope: str = Query("month", description="week | month | year"),
    year: Optional[int] = Query(None, description="YYYY (opsional, default: sekarang)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="1-12, untuk scope=month"),
    week: Optional[int] = Query(None, ge=1, le=53, description="ISO week, untuk scope=week"),
) -> Dict[str, Any]:
    try:
        today = date.today()
        if scope not in {"week", "month", "year"}:
            scope = "month"
        y = year or today.year
        m = month or (today.month if scope == "month" else None)
        if scope == "week":
            # gunakan ISO week default: minggu ini
            iso = today.isocalendar()
            w = week or int(iso[1])
            iso_year = y  # asumsi tahun ISO = year param (cukup untuk keperluan kita)
        else:
            w = None
            iso_year = None

        col = get_collection()
        # ChromaDB no longer allows "ids" in include; ids are always returned
        got = col.get(include=["documents", "metadatas"], limit=100000)
        docs: List[str] = got.get("documents") or []
        ids: List[str] = got.get("ids") or []
        metas: List[dict] = got.get("metadatas") or []

        totals: Dict[str, Dict[str, Any]] = {}
        rx = re.compile(r"(20\d{2})-(\d{2})-(\d{2}).*?sejauh\s+([0-9]+(?:[.,][0-9]+)?)\s*km", re.IGNORECASE)

        for i, text in enumerate(docs):
            member = None
            md = metas[i] if i < len(metas) else {}
            if isinstance(md, dict) and md.get("member_name"):
                member = str(md["member_name"]).strip()
            if not member:
                member = (ids[i] if i < len(ids) else f"member-{i}")

            if not text:
                continue

            for match in rx.finditer(text):
                yy, mm, dd, km = match.groups()
                try:
                    dt = date(int(yy), int(mm), int(dd))
                    val = float(km.replace(",", "."))
                except Exception:
                    continue

                ok = False
                if scope == "year":
                    ok = (dt.year == y)
                elif scope == "month":
                    ok = (dt.year == y and dt.month == (m or today.month))
                elif scope == "week":
                    iso_info = dt.isocalendar()  # (iso_year, iso_week, iso_weekday)
                    ok = (iso_info[0] == (iso_year or y) and iso_info[1] == (w or 1))

                if not ok:
                    continue

                if member not in totals:
                    totals[member] = {"member": member, "total_km": 0.0, "activities": 0}
                totals[member]["total_km"] += val
                totals[member]["activities"] += 1

        # sort desc by total_km
        board = sorted(totals.values(), key=lambda x: x["total_km"], reverse=True)
        return {
            "status": "ok",
            "scope": scope,
            "year": y,
            "month": m,
            "week": w,
            "leaderboard": [
                {"rank": i + 1, **{"member": r["member"], "total_km": round(r["total_km"], 2), "activities": r["activities"]}}
                for i, r in enumerate(board)
            ],
            "time": now_str(),
        }
    except Exception as e:
        logger.exception(f"/leaderboard error: {e}")
        return {"status": "error", "message": str(e), "time": now_str()}
