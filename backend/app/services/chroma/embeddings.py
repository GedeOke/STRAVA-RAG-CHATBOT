from app.core.logger import logger
from app.core.config import settings
from sentence_transformers import SentenceTransformer
import numpy as np


# ==================================================
# LOAD MODEL SEKALI SAJA
# ==================================================
try:
    logger.info(f"Memuat model embedding: {settings.EMBEDDING_MODEL}")
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
except Exception as e:
    logger.exception(f"Gagal memuat model embedding: {e}")
    model = None


# ==================================================
# ENCODE TEKS KE VEKTOR
# ==================================================
def embed_texts(texts):
    """
    Ubah list teks jadi list embedding (list of floats).
    Return: list[np.ndarray]
    """
    try:
        if not model:
            raise ValueError("Model embedding belum dimuat.")
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        logger.info(f"Embedding {len(texts)} teks berhasil dibuat.")
        return embeddings.tolist() if isinstance(embeddings, np.ndarray) else embeddings
    except Exception as e:
        logger.exception(f"Gagal generate embedding: {e}")
        return []

