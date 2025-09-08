from sqlalchemy.orm import Session
from sqlalchemy import text
from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
import re
import traceback

print("LOADED retriever.py FROM:", __file__)

# Bi-encoder (sama dengan yang dipakai saat generate embeddings)
_bi = SentenceTransformer("all-mpnet-base-v2")

# Cross-encoder untuk re-ranking (lazy-init supaya startup cepat)
_ce = None

# -------- helpers --------

# pgvector literal HARUS pakai bracket [ ... ]
def _to_pgvector(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"

# Parse angka jarak dari query: 5km, 5 km, 5k, 5000m, 5K, dst → km (float) atau None
_DIST_RES = [
    re.compile(r'(\d+(?:\.\d+)?)\s*(km|kilometer)\b', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*(k)\b', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*(m|meter|metre)\b', re.I),
]
def _parse_km(q: str):
    s = q.strip().replace(" ", "")
    for rx in _DIST_RES:
        m = rx.search(s)
        if not m:
            continue
        val = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ("km", "kilometer"):
            return val
        if unit == "k":
            return val  # 5k → 5.0 km
        if unit in ("m", "meter", "metre"):
            return val / 1000.0
    return None

# Query expansion ringan utk angka jarak
def _expand_queries(q: str):
    exps = {q}
    km = _parse_km(q)
    if km:
        km_i = int(round(km))
        exps |= {
            f"lari {km} km",
            f"lari {km_i} km",
            f"lari {km_i}k",
            f"lari {int(km*1000)} meter",
        }
        if km_i == 5:
            exps |= {"lari 5k", "lari lima kilometer"}
    return list({e for e in exps if e})

def _ensure_ce():
    global _ce
    if _ce is None:
        _ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _ce

# -------- main search --------

def search_similar(
    db: Session,
    query: str,
    top_k: int = 5,
    tol: float = 0.20,         # toleransi ±20% utk filter jarak
    candidates: int = 40,      # kandidat awal per ekspansi
    alpha_km: float = 0.6      # bobot penalti selisih km (untuk hybrid)
):
    """
    3 tahap:
      1) Candidate retrieval (bi-encoder) + structured filter jarak (JOIN activities + BETWEEN)
      2) Pool dari beberapa query expansion
      3) Re-rank dengan cross-encoder + penalti selisih km
    """
    try:
        want_km = _parse_km(query)
        exps = _expand_queries(query)

        # pool kandidat dari semua ekspansi
        pool = {}  # id -> best item
        for q in exps:
            # embed query ekspansi
            q_emb = _bi.encode([q])[0].astype(np.float32)
            qvec_lit = _to_pgvector(q_emb)

            where_dist = ""
            if want_km is not None:
                dmin = int(1000 * (want_km * (1 - tol)))
                dmax = int(1000 * (want_km * (1 + tol)))
                where_dist = f"AND a.distance_m BETWEEN {dmin} AND {dmax}"

            sql = text(f"""
                SELECT s.id, s.summary, a.distance_m,
                       (s.embedding <-> (:qvec)::vector) AS emb_dist
                FROM activity_summaries s
                JOIN activities a ON a.id = s.activity_id
                WHERE s.embedding IS NOT NULL
                {where_dist}
                ORDER BY s.embedding <-> (:qvec)::vector
                LIMIT :lim
            """)
            rows = db.execute(sql, {"qvec": qvec_lit, "lim": int(candidates)}).fetchall()

            # masukkan ke pool, simpan yang emb_dist terbaik per id
            for r in rows:
                rid = r.id
                km_val = (r.distance_m or 0) / 1000.0 if r.distance_m is not None else None
                item = {
                    "id": rid,
                    "summary": r.summary,
                    "km": km_val,
                    "emb_dist": float(r.emb_dist),
                }
                if rid not in pool or item["emb_dist"] < pool[rid]["emb_dist"]:
                    pool[rid] = item

        items = list(pool.values())
        if not items:
            return []

        # skor hybrid awal: embedding distance + penalti selisih km
        if want_km is not None:
            for it in items:
                km_gap = abs((it["km"] or 0) - want_km)
                it["hybrid"] = it["emb_dist"] + alpha_km * km_gap
        else:
            for it in items:
                it["hybrid"] = it["emb_dist"]

        # Re-rank pakai cross-encoder (kalau modelnya tersedia)
        try:
            ce = _ensure_ce()
            pairs = [(query, it["summary"]) for it in items]
            ce_scores = ce.predict(pairs)  # tinggi = lebih relevan
            for it, sc in zip(items, ce_scores):
                it["ce_score"] = float(sc)
            # urutkan: CE desc (terbaik dulu), tie-break hybrid
            items.sort(key=lambda x: (-x["ce_score"], x["hybrid"], x["emb_dist"]))
        except Exception:
            # fallback kalau CE gagal
            traceback.print_exc()
            items.sort(key=lambda x: (x["hybrid"], x["emb_dist"]))

        return [
            {
                "id": it["id"],
                "summary": it["summary"],
                "km": it["km"],
                "emb_dist": it["emb_dist"],
                "ce_score": it.get("ce_score"),
            }
            for it in items[:top_k]
        ]

    except Exception:
        traceback.print_exc()
        raise
