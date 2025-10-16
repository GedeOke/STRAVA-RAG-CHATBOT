from loguru import logger
import sys
import os
from datetime import datetime

# ==================================================
# Folder logs otomatis dibuat kalau belum ada
# ==================================================
LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ==================================================
# Nama file log pakai timestamp (rotasi harian)
# ==================================================
LOG_FILE = os.path.join(LOG_DIR, f"app_{datetime.now().strftime('%Y-%m-%d')}.log")

# ==================================================
# Konfigurasi Loguru
# ==================================================
logger.remove()  # hapus handler default
logger.add(
    sys.stdout,
    colorize=True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    level="INFO",
)

# simpan juga ke file
logger.add(
    LOG_FILE,
    rotation="00:00",       # buat file baru tiap tengah malam
    retention="7 days",     # simpan log selama 7 hari
    compression="zip",      # compress log lama
    level="INFO",
    enqueue=True,           # thread-safe
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
)


# ==================================================
# Helper function buat log error di try-except
# ==================================================
def log_try(func):
    """
    Dekorator untuk auto logging error di fungsi manapun.
    Contoh:
    @log_try
    def sync_data(): ...
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Unhandled error in {func.__name__}: {e}")
            raise e

    return wrapper


# ==================================================
# Tes awal
# ==================================================
if __name__ == "__main__":
    logger.info("Logger initialized successfully.")

