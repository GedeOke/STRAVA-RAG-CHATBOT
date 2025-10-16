from app.services.chroma.db_client import get_collection, get_chroma_client
from app.core.logger import logger
from app.core.config import settings


# ==================================================
# INSERT / UPSERT DOCUMENT
# ==================================================
def upsert_document(doc_id: str, text: str, embedding: list, metadata: dict = None):
    """Upsert dokumen (insert atau update kalau sudah ada)."""
    try:
        collection = get_collection()
        collection.upsert(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}],
        )
        logger.info(f"Upsert dokumen '{doc_id}' berhasil.")
    except Exception as e:
        logger.exception(f"Gagal upsert dokumen '{doc_id}': {e}")


# ==================================================
# QUERY / RETRIEVE
# ==================================================
def query_documents(query_emb: list, top_k: int = 5):
    """Ambil dokumen paling relevan berdasarkan embedding query."""
    try:
        collection = get_collection()
        results = collection.query(query_embeddings=query_emb, n_results=top_k)
        count = len(results.get("documents", [[]])[0])
        logger.info(f"Query menghasilkan {count} dokumen relevan.")
        return results
    except Exception as e:
        logger.exception(f"Gagal query dokumen: {e}")
        return {"documents": [[]]}


# ==================================================
# DELETE DOCUMENT
# ==================================================
def delete_document(doc_id: str):
    """Hapus satu dokumen berdasarkan ID."""
    try:
        collection = get_collection()
        collection.delete(ids=[doc_id])
        logger.info(f"Dokumen '{doc_id}' berhasil dihapus.")
    except Exception as e:
        logger.exception(f"Gagal hapus dokumen '{doc_id}': {e}")


# ==================================================
# RESET SEMUA
# ==================================================
def reset_collection():
    """Hapus semua isi koleksi (warning!)."""
    try:
        client = get_chroma_client()
        try:
            client.delete_collection(settings.CHROMA_COLLECTION)
            logger.warning("Koleksi ChromaDB dihapus. Akan dibuat ulang saat next access.")
        except Exception:
            # Jika delete_collection tidak tersedia/bermasalah, fallback delete by ids
            collection = get_collection()
            got = collection.get(include=["ids"], limit=100000)
            ids = got.get("ids") or []
            if ids:
                collection.delete(ids=ids)
            logger.warning("Semua dokumen di koleksi ChromaDB telah dihapus (fallback by ids).")
    except Exception as e:
        logger.exception(f"Gagal reset koleksi: {e}")
