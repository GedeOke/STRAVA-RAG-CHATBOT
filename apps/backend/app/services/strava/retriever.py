from sqlalchemy.orm import Session
from sqlalchemy import text
from sentence_transformers import SentenceTransformer
import numpy as np
import traceback

print("LOADED retriever.py FROM:", __file__)

# Pakai model yang sama dengan saat generate embeddings (768 dim)
_model = SentenceTransformer("all-mpnet-base-v2")

def _to_pgvector(vec: np.ndarray) -> str:
    # >>> pgvector literal HARUS pakai [ ... ] bukan { ... }
    return "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"

def search_similar(db: Session, query: str, top_k: int = 5):
    try:
        emb = _model.encode([query])[0]
        emb = np.asarray(emb, dtype=np.float32)

        qvec_lit = _to_pgvector(emb)  # contoh: "[0.123,-0.456,...]"

        sql = text("""
            SELECT id, summary, (embedding <-> (:qvec)::vector) AS distance
            FROM activity_summaries
            WHERE embedding IS NOT NULL
            ORDER BY embedding <-> (:qvec)::vector
            LIMIT :k
        """)

        rows = db.execute(sql, {"qvec": qvec_lit, "k": int(top_k)}).fetchall()


        return [{"id": r.id, "summary": r.summary, "distance": float(r.distance)} for r in rows]

    except Exception as e:
        traceback.print_exc()
        # biar FastAPI kirim detail ke klien
        raise
