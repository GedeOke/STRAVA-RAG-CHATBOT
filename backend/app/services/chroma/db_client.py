from app.core.config import settings
from app.core.logger import logger
import chromadb
import os


# ==================================================
# INIT CHROMA CLIENT
# ==================================================
def get_chroma_client():
    """Inisialisasi koneksi ke ChromaDB persistent client."""
    try:
        os.makedirs(settings.CHROMA_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        logger.info(f"Chroma client connected at {settings.CHROMA_PATH}")
        return client
    except Exception as e:
        logger.exception(f"Gagal konek ke ChromaDB: {e}")
        raise e


# ==================================================
# INIT / GET COLLECTION
# ==================================================
def get_collection():
    """Mengambil atau membuat koleksi default (strava_club)."""
    try:
        client = get_chroma_client()
        collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION)
        logger.info(f"Collection aktif: {settings.CHROMA_COLLECTION}")
        return collection
    except Exception as e:
        logger.exception(f"Gagal membuat/mengambil koleksi: {e}")
        raise e

