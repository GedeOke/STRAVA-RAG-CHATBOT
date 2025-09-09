from sqlalchemy.orm import Session
from sqlalchemy import text
from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
import re
import traceback

print("LOADED retriever.py FROM:", __file__)

# -------- models --------
# Bi-encoder (sama dgn yang dipakai waktu generate embeddings)
_bi = SentenceTransformer("all-mpnet-base-v2")

# Cross-encoder untuk re-ranking (lazy init)
_ce = None


# -------- helpers --------
def _to_pgvector(vec: np.ndarray) -> str:
    """pgvector literal HARUS pakai bracket [ ... ]"""
    return "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"

# deteksi angka jarak -> km float
_RX_KM = [
    re.compile(r'(\d+(?:\.\d+)?)\s*(km|kilometer)\b', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*(k)\b', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*(m|meter|metre)\b', re.I),
]
def _parse_km(q: str):
    s = q.strip()
    for rx in _RX_KM:
        m = rx.search(s)
        if not m:
            continue
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("km", "kilometer"):
            return val
        if unit == "k":
            return val
        if unit in ("m", "meter", "metre"):
            return val / 1000.0
    return None

def _expand_terms(q: str) -> list[str]:
    """AQE ringan: tambah sinonim + normalisasi angka jarak (ID-first)."""
    q0 = q.strip()
    out = [q0]

    # sinonim umum
    out += ["lari", "running", "run", "jogging"]

    km = _parse_km(q0)
    if km is not None:
        km_i = int(round(km))
        out += [
            f"lari {km:.1f} km",
            f"lari {km_i} km",
            f"{km_i}k run",
            f"jogging {km_i} km",
            f"{int(km*1000)} meter",
        ]
        if km_i == 5:
            out += ["lari 5k", "lari lima kilometer"]

    # dedup, buang kosong, batasi 6 term biar embed cepat
    seen, uniq = set(), []
    for t in out:
        t = t.strip()
        if not t: 
            continue
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:6]

def _encode_mean(terms: list[str]) -> np.ndarray:
    """Encode semua terms -> rata-rata (Aligned Query Expansion)."""
    vecs = _bi.encode(terms)
    emb = np.asarray(vecs, dtype=np.float32).mean(axis=0)
    return emb

def _ensure_ce():
    global _ce
    if _ce is None:
        _ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _ce


# -------- main search --------
def search_similar(
    db: Session,
    query: str,
    top_k: int = 50,
    tol: float = 0.20,       # toleransi ±20% utk filter jarak (kalau query menyebut jarak)
    candidates: int = 80,    # banyak kandidat awal dari pgvector
    alpha_km: float = 0.6    # bobot penalti selisih km (semakin besar, makin strict ke jarak)
):
    """
    Pipeline:
    1) Aligned Query Expansion -> average pooling => single query embedding
    2) Candidate retrieval (pgvector) + optional structured filter jarak
    3) Re-ranking CrossEncoder + hybrid penalty (emb_dist + alpha*|km_gap|)
    """

    try:
        # (opsional) tuning ivfflat
        try:
            db.execute(text("SET ivfflat.probes = 10"))
        except Exception:
            pass  # kalau extension/konfigurasi gak ada, lanjut saja

        # --- (1) AQE: perluas query -> rata-rata embedding
        terms = _expand_terms(query)
        q_emb = _encode_mean(terms)
        qvec_lit = _to_pgvector(q_emb)

        # --- (2) Candidate retrieval + filter jarak
        want_km = _parse_km(query)
        where_dist = ""
        if want_km is not None:
            dmin = int(1000 * (want_km * (1 - tol)))
            dmax = int(1000 * (want_km * (1 + tol)))
            where_dist = f"AND a.distance_m BETWEEN {dmin} AND {dmax}"

        # ✅ UPDATE: summary diperjelas (gabung nama atlet + jenis olahraga + nama + jarak)
        sql = text(f"""
            SELECT a.id,
                concat(at.firstname, ' ', at.lastname,
                        ' melakukan ', a.sport_type,
                        ' \"', a.name, '\" sejauh ',
                        round((a.distance_m/1000.0)::numeric, 2), ' km') AS summary,
                a.distance_m,
                (a.embedding <-> (:qvec)::vector) AS emb_dist
            FROM activities a
            JOIN athletes at ON a.athlete_id = at.id
            WHERE a.embedding IS NOT NULL
            {where_dist}
            ORDER BY a.embedding <-> (:qvec)::vector
            LIMIT :lim
        """)

        rows = db.execute(sql, {"qvec": qvec_lit, "lim": int(candidates)}).fetchall()

        if not rows:
            return []

        items = []
        for r in rows:
            km_val = (r.distance_m or 0) / 1000.0 if r.distance_m is not None else None
            items.append({
                "id": r.id,
                "summary": r.summary,   # sekarang isi = kalimat deskriptif
                "km": km_val,
                "emb_dist": float(r.emb_dist),
            })

        # hybrid baseline: emb_dist + penalty selisih km
        if want_km is not None:
            for it in items:
                km_gap = abs((it["km"] or 0) - want_km)
                it["hybrid"] = it["emb_dist"] + alpha_km * km_gap
        else:
            for it in items:
                it["hybrid"] = it["emb_dist"]

        # --- (3) Re-rank pakai CrossEncoder (desc), tie-break hybrid
        try:
            ce = _ensure_ce()
            pairs = [(query, it["summary"]) for it in items]
            ce_scores = ce.predict(pairs)  # tinggi = lebih relevan
            for it, sc in zip(items, ce_scores):
                it["ce_score"] = float(sc)
            items.sort(key=lambda x: (-x["ce_score"], x["hybrid"], x["emb_dist"]))
        except Exception:
            traceback.print_exc()
            # fallback tanpa CE
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
