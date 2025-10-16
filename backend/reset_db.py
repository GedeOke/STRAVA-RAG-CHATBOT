from app.services.chroma.manager import reset_collection
from app.core.logger import logger
import os


CACHE_PATH = "./cache/cache_hash.json"


def main():
    try:
        logger.warning("Memulai reset koleksi ChromaDB...")
        reset_collection()

        if os.path.exists(CACHE_PATH):
            os.remove(CACHE_PATH)
            logger.info("Cache hash dihapus.")
        else:
            logger.info("Cache hash tidak ditemukan, lewati.")

        logger.warning("Reset selesai.")
    except Exception as e:
        logger.exception(f"Gagal reset database/cache: {e}")


if __name__ == "__main__":
    main()
