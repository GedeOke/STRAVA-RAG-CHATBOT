from sentence_transformers import SentenceTransformer
import numpy as np

# pake model ringan dulu biar cepat
_model = SentenceTransformer("all-mpnet-base-v2")

def embed_text(text: str) -> np.ndarray:
    """Generate embedding dari teks summary"""
    vec = _model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return vec[0]
