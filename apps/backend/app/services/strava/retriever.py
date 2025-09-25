# apps/backend/app/services/strava/retriever.py
from __future__ import annotations
import logging
import re
import traceback
from functools import lru_cache
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session
from sentence_transformers import SentenceTransformer, CrossEncoder

print("LOADED retriever.py FROM:", __file__)

# =========================
# Models
# =========================
_BI = SentenceTransformer("all-mpnet-base-v2")  # sama dgn saat generate embeddings
_CE = None
_CE_FAILED = False


def _ensure_ce():
    global _CE, _CE_FAILED
    if _CE is None and not _CE_FAILED:
        try:
            _CE = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logging.info("CrossEncoder loaded")
        except Exception as e:
            logging.error(f"Gagal load CrossEncoder: {e}")
            _CE_FAILED = True
            _CE = None
    return _CE


# =========================
# Parsing & Helpers
# =========================
_RX_KM = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(km|kilometer)\b", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*k\b", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(m|meter|metre)\b", re.I),
]


def _parse_km(q: str) -> float | None:
    for rx in _RX_KM:
        m = rx.search(q)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "k").lower()
            if unit in ("km", "kilometer", "k"):
                return val
            if unit in ("m", "meter", "metre"):
                return val / 1000.0
    return None


def _parse_time_range(q: str) -> Tuple[datetime | None, datetime | None]:
    now = datetime.utcnow()
    ql = q.lower()
    if "hari ini" in ql:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if "kemarin" in ql:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if "minggu ini" in ql:
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if "bulan ini" in ql:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    return None, None


def _to_pgvector(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"


def _expand_terms(q: str, max_terms: int = 6) -> List[str]:
    q0 = q.strip()
    out = [q0, "lari", "running", "run", "jogging"]
    km = _parse_km(q0)
    if km is not None:
        kmi = int(round(km))
        out += [
            f"lari {km:.1f} km",
            f"lari {kmi} km",
            f"{kmi}k run",
            f"jogging {kmi} km",
            f"{int(km*1000)} meter",
        ]
    return list(dict.fromkeys(out))[:max_terms]


@lru_cache(maxsize=256)
def _encode_query_cached(query_key: str) -> np.ndarray:
    terms = _expand_terms(query_key)
    vecs = _BI.encode(terms, convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32).mean(axis=0)


# =========================
# Main Search
# =========================
def search_similar(
    db: Session,
    query: str,
    top_k: int = 50,
    candidates: int = 80,
    alpha_km: float = 0.6,
) -> List[Dict[str, Any]]:
    """
    1) AQE ringan -> embedding rata-rata
    2) Candidate retrieval (pgvector + filter jarak & waktu statis)
    3) Hybrid scoring + (opsional) CrossEncoder re-rank
    """
    try:
        q_emb = _encode_query_cached(query)
        qvec_lit = _to_pgvector(q_emb)

        want_km = _parse_km(query)
        start, end = _parse_time_range(query)

        where_dist, where_date, params = "", "", {"qvec": qvec_lit, "lim": int(candidates)}

        if want_km is not None:
            # static tolerance ±0.3 km
            dmin = int(1000 * (want_km - 0.3))
            dmax = int(1000 * (want_km + 0.3))
            if dmin < 0:
                dmin = 0
            where_dist = "AND a.distance_m BETWEEN :dmin AND :dmax"
            params.update({"dmin": dmin, "dmax": dmax})

        if start and end:
            where_date = "AND a.date BETWEEN :dstart AND :dend"
            params.update({"dstart": start, "dend": end})

        sql = text(f"""
            SELECT a.id, a.name, a.sport_type, a.distance_m,
                   at.firstname, at.lastname,
                   (a.embedding <-> (:qvec)::vector) AS emb_dist
            FROM activities a
            JOIN athletes at ON a.athlete_id = at.id
            WHERE a.embedding IS NOT NULL
            {where_dist}
            {where_date}
            ORDER BY a.embedding <-> (:qvec)::vector
            LIMIT :lim
        """)

        rows = db.execute(sql, params).fetchall()
        if not rows:
            return []

        items = []
        for r in rows:
            km_val = (r.distance_m or 0) / 1000.0 if r.distance_m else None
            summary = f"{r.firstname} {r.lastname} melakukan {r.sport_type} \"{r.name}\" sejauh {km_val:.2f} km"
            items.append({
                "id": r.id,
                "summary": summary,
                "km": km_val,
                "emb_dist": float(r.emb_dist),
            })

        # hybrid score baseline
        for it in items:
            if want_km is not None:
                km_gap = abs((it["km"] or 0) - want_km)
                it["hybrid"] = it["emb_dist"] + alpha_km * km_gap
            else:
                it["hybrid"] = it["emb_dist"]

        # re-rank dengan CE kalau ada
        ce = _ensure_ce()
        if ce is not None:
            try:
                pairs = [(query, it["summary"]) for it in items]
                ce_scores = ce.predict(pairs)
                for it, sc in zip(items, ce_scores):
                    it["ce_score"] = float(sc)
                items.sort(key=lambda x: (-x["ce_score"], x["hybrid"]))
            except Exception as e:
                logging.warning(f"CrossEncoder error: {e}, fallback hybrid")
                items.sort(key=lambda x: (x["hybrid"], x["emb_dist"]))
        else:
            items.sort(key=lambda x: (x["hybrid"], x["emb_dist"]))

        return items[:top_k]

    except Exception as e:
        logging.error("search_similar error", exc_info=True)
        return []


def search_with_intent(db: Session, query: str, intent: str) -> Dict[str, Any]:
    results = search_similar(db, query)
    if intent == "count":
        return {"count": len(results), "activities": results}
    if intent == "who":
        members = {r["summary"].split(" ")[0] for r in results}
        return {"members": list(members), "activities": results}
    if intent == "top":
        return {"top": results[:1], "activities": results}
    return {"activities": results}
