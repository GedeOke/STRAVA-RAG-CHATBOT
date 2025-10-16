from fastapi import APIRouter
from app.core.logger import logger
from app.core.utils import now_str
from app.core.config import settings
import os


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
def health_check():
    """
    Endpoint untuk ngecek apakah API hidup dan konfigurasi dasar aman.
    """
    try:
        chroma_exists = os.path.exists(settings.CHROMA_PATH)
        message = {
            "status": "ok",
            "project": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "time": now_str(),
            "chroma_path": settings.CHROMA_PATH,
            "chroma_exists": chroma_exists,
        }

        logger.info(f"Health check: OK - {settings.PROJECT_NAME}")
        return message

    except Exception as e:
        logger.exception(f"Health check gagal: {e}")
        return {
            "status": "error",
            "message": str(e),
            "time": now_str(),
        }

